"""Unified seeding utility for the accounting LLM framework.

**Single source of truth for all deterministic seeds in this repo.** The
project's seed-derivation policy is "trace every `seed_int` back to a
`seedhash.SeedHashGenerator(...)` call" — no hand-picked integers, no
`seed_int + rank` arithmetic. This module is the only place a code path
should pull a seed from. See `eval/README.md` §Seeding policy and the
project memory `seeding_policy.md` for the doctrine.

Coverage tiers
--------------

| Tier                       | What gets seeded                                                      |
|---|---|
| CPU                        | `PYTHONHASHSEED`, Python `random`, NumPy                              |
| Single GPU                 | + `torch.manual_seed`, `torch.cuda.manual_seed_all`                   |
| Multi-GPU one host (DDP)   | + per-rank seed via salted `seedhash`, DataLoader `worker_init_fn`    |
| Multi-GPU multi host       | + same per-rank derivation; rank discovered via `torch.distributed`   |

Topology is auto-detected from `torch.distributed` if initialized, else
from `RANK` / `WORLD_SIZE` / `LOCAL_RANK` / `LOCAL_WORLD_SIZE` env vars
(set by `torchrun` / `deepspeed` / `accelerate launch`), else single-process
defaults.

Strict mode (opt-in)
--------------------

`strict=True` flips on the slow-but-bit-exact CUDA path:

- `torch.use_deterministic_algorithms(True, warn_only=True)`
- `torch.backends.cudnn.deterministic = True`
- `torch.backends.cudnn.benchmark = False`
- `CUBLAS_WORKSPACE_CONFIG=:4096:8`

Use for ablation-grade reproducibility runs only; non-strict default keeps
cuDNN autotune on and throughput high while still producing a deterministic
*sampling* path.

Typical use
-----------

```python
from eval.seeding import seed_everything

# Path A — pass the split's seed_int directly (matches existing recipes).
report = seed_everything(seed_int=351199285)

# Path B — derive from the seedhash input string (the canonical path).
report = seed_everything(
    seedhash_input="spiceland9e-finetune-robustness-2026-05-19",
    seed_index=0,
)

# Embed in manifest.json
manifest["seeding_report"] = report.to_dict()
```

For DataLoader workers (multi-worker dataloading):

```python
from torch.utils.data import DataLoader
loader = DataLoader(
    ds,
    num_workers=4,
    worker_init_fn=report.worker_init_fn,  # per-rank seed + worker_id
    generator=report.torch_generator,       # for shuffling determinism
)
```
"""
from __future__ import annotations

import hashlib
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import seedhash  # PyPI: https://pypi.org/project/seedhash/

# Defaults — match `eval/split_multi_seed.py` so the same `seedhash_input`
# produces the same `seed_int` sequence as the splits.
DEFAULT_SEEDHASH_INPUT = "spiceland9e-finetune-robustness-2026-05-19"
DEFAULT_N_SEEDS = 5


# ---------------------------------------------------------------------------
# Public dataclass — embed `report.to_dict()` in manifest.json
# ---------------------------------------------------------------------------

@dataclass
class SeedingReport:
    """Snapshot of what `seed_everything` actually applied. Embed in
    `manifest.json` so a replay can verify the seeding chain was identical.
    """

    seedhash_input: str | None
    seedhash_package_version: str | None
    seed_index: int | None
    seed_int: int
    per_rank_seed_int: int
    rank: int
    world_size: int
    local_rank: int
    local_world_size: int
    topology: str   # "cpu" | "single_gpu" | "multi_gpu_single_host" | "multi_host"
    strict: bool
    applied: dict[str, Any] = field(default_factory=dict)
    # Non-serialized handles attached by `seed_everything` for runtime use.
    worker_init_fn: Callable[[int], None] | None = field(default=None, repr=False)
    torch_generator: Any | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe view for manifest.json — drops the runtime handles."""
        return {
            "seedhash_input": self.seedhash_input,
            "seedhash_package_version": self.seedhash_package_version,
            "seed_index": self.seed_index,
            "seed_int": self.seed_int,
            "per_rank_seed_int": self.per_rank_seed_int,
            "rank": self.rank,
            "world_size": self.world_size,
            "local_rank": self.local_rank,
            "local_world_size": self.local_world_size,
            "topology": self.topology,
            "strict": self.strict,
            "applied": self.applied,
        }


# ---------------------------------------------------------------------------
# Seed derivation — all paths funnel through `seedhash.SeedHashGenerator`
# ---------------------------------------------------------------------------

def _seedhash_version() -> str:
    return getattr(seedhash, "__version__", "unknown")


def generate_seeds(seedhash_input: str, n: int) -> list[int]:
    """Mirror of `eval/split_multi_seed.py`'s call. Single source of truth
    for the `seedhash_input → list[seed_int]` mapping."""
    gen = seedhash.SeedHashGenerator(seedhash_input)
    return gen.generate_seeds(n)


def derive_per_rank_seed(
    seedhash_input: str,
    seed_index: int,
    rank: int,
) -> int:
    """Per-rank seed for distributed training.

    Discipline: salt the seedhash input with the seed_index and rank, then
    call `seedhash` again. Avoids `seed_int + rank` arithmetic, which can
    collide when two adjacent seeds happen to be close. Returns the first
    seed of a 1-seed generator run on the salted input.

    Salt format: `f"{seedhash_input}|seed_{seed_index:02d}|rank_{rank:04d}"`.
    """
    salt = f"{seedhash_input}|seed_{seed_index:02d}|rank_{rank:04d}"
    return generate_seeds(salt, 1)[0]


# ---------------------------------------------------------------------------
# Topology detection
# ---------------------------------------------------------------------------

def _detect_topology() -> tuple[str, int, int, int, int, int]:
    """Return (topology, rank, world_size, local_rank, local_world_size, n_gpus_host).

    Sources, in priority order:
      1. `torch.distributed` if initialized.
      2. `RANK` / `WORLD_SIZE` / `LOCAL_RANK` / `LOCAL_WORLD_SIZE` env vars
         (set by torchrun / accelerate launch / deepspeed).
      3. Single-process defaults.
    """
    rank = int(os.environ.get("RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    local_world_size = int(os.environ.get("LOCAL_WORLD_SIZE", str(world_size)))

    n_gpus_host = 0
    try:
        import torch
        if torch.distributed.is_available() and torch.distributed.is_initialized():
            rank = torch.distributed.get_rank()
            world_size = torch.distributed.get_world_size()
        if torch.cuda.is_available():
            n_gpus_host = torch.cuda.device_count()
    except ImportError:
        pass

    if world_size > local_world_size and world_size > 1:
        topology = "multi_host"
    elif world_size > 1 and n_gpus_host > 1:
        topology = "multi_gpu_single_host"
    elif n_gpus_host >= 1:
        topology = "single_gpu"
    else:
        topology = "cpu"

    return topology, rank, world_size, local_rank, local_world_size, n_gpus_host


# ---------------------------------------------------------------------------
# Worker init fn for DataLoader determinism across workers
# ---------------------------------------------------------------------------

def _build_worker_init_fn(per_rank_seed: int) -> Callable[[int], None]:
    """Return a `worker_init_fn` that re-seeds each DataLoader worker
    deterministically as `per_rank_seed + worker_id`. PyTorch already seeds
    `torch` per-worker via the `base_seed + worker_id` formula; this adds
    Python `random` and NumPy on top so user-side libraries imported by the
    dataset code path also see deterministic randomness.
    """
    def _init(worker_id: int) -> None:
        worker_seed = per_rank_seed + worker_id
        random.seed(worker_seed)
        try:
            import numpy as np
            np.random.seed(worker_seed % (2**32 - 1))
        except ImportError:
            pass
    return _init


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def seed_everything(
    *,
    seedhash_input: str | None = None,
    seed_index: int | None = None,
    seed_int: int | None = None,
    strict: bool = False,
    verbose: bool = True,
) -> SeedingReport:
    """Apply deterministic seeds across all four coverage tiers.

    Seed resolution (exactly one of the two paths):

    - `seed_int=<int>` — pass through directly. Use this when re-using the
      split's `seed_int` (e.g. `351199285` for seed_00). The `seedhash_input`
      + `seed_index` fields in the report will be `None`.
    - `seedhash_input=<str>, seed_index=<int>` — derive via
      `seedhash.SeedHashGenerator(seedhash_input).generate_seeds(seed_index+1)[seed_index]`.
      Canonical for fresh-experiment derivations.

    For multi-GPU / multi-host, the *base* `seed_int` is broadcast logically
    (every rank computes the same base), and a *per-rank* seed is derived
    via `derive_per_rank_seed` from the salted `seedhash` path. Pass the
    `worker_init_fn` and `torch_generator` on the returned `SeedingReport`
    into your DataLoader.

    Strict mode is opt-in. See module docstring.
    """
    # ── resolve base seed_int ───────────────────────────────────────────────
    if seed_int is None:
        if seedhash_input is None or seed_index is None:
            raise ValueError(
                "seed_everything: pass either `seed_int=<int>` or both "
                "`seedhash_input=<str>` and `seed_index=<int>`."
            )
        seeds = generate_seeds(seedhash_input, seed_index + 1)
        if seed_index >= len(seeds):
            raise ValueError(
                f"seed_index={seed_index} out of range for the "
                f"seedhash sequence generated from {seedhash_input!r}."
            )
        base_seed = seeds[seed_index]
    else:
        if seedhash_input is not None or seed_index is not None:
            if verbose:
                print(
                    "[seeding] both `seed_int` and `seedhash_input`/`seed_index` given; "
                    "using `seed_int` directly and ignoring the seedhash path.",
                    file=sys.stderr,
                )
        base_seed = seed_int

    # ── topology ────────────────────────────────────────────────────────────
    topology, rank, world_size, local_rank, local_world_size, n_gpus_host = _detect_topology()

    # ── per-rank seed ───────────────────────────────────────────────────────
    if topology in ("multi_gpu_single_host", "multi_host"):
        # Multi-rank: derive a fresh seedhash-rooted seed per rank.
        rank_salt_input = seedhash_input if seedhash_input is not None else f"seed_int_{base_seed}"
        rank_salt_index = seed_index if seed_index is not None else 0
        per_rank_seed = derive_per_rank_seed(rank_salt_input, rank_salt_index, rank)
    else:
        # Single-process / single-GPU: rank-0 seed == base seed.
        per_rank_seed = base_seed

    # ── apply CPU layer ─────────────────────────────────────────────────────
    applied: dict[str, Any] = {}

    # PYTHONHASHSEED has to be set before the interpreter starts to affect
    # hash randomization, so this is mostly documentary. We set it anyway
    # for any sub-process spawn that re-reads env.
    os.environ["PYTHONHASHSEED"] = str(per_rank_seed)
    applied["PYTHONHASHSEED"] = str(per_rank_seed)
    applied["python_random.seed"] = per_rank_seed
    random.seed(per_rank_seed)

    try:
        import numpy as np
        np_seed = per_rank_seed % (2**32 - 1)
        np.random.seed(np_seed)
        applied["numpy.random.seed"] = np_seed
    except ImportError:
        applied["numpy.random.seed"] = "skipped (numpy not importable)"

    # ── apply GPU layer ─────────────────────────────────────────────────────
    torch_generator = None
    try:
        import torch
        torch.manual_seed(per_rank_seed)
        applied["torch.manual_seed"] = per_rank_seed
        if torch.cuda.is_available():
            torch.cuda.manual_seed(per_rank_seed)
            torch.cuda.manual_seed_all(per_rank_seed)   # all visible CUDA devices
            applied["torch.cuda.manual_seed_all"] = per_rank_seed

        # Generator handle for DataLoader shuffling determinism
        torch_generator = torch.Generator()
        torch_generator.manual_seed(per_rank_seed)
        applied["torch.Generator"] = per_rank_seed

        # Strict-determinism flags (opt-in; cost throughput)
        if strict:
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
            try:
                torch.use_deterministic_algorithms(True, warn_only=True)
                applied["torch.use_deterministic_algorithms"] = True
            except Exception as exc:
                applied["torch.use_deterministic_algorithms"] = f"failed ({exc!s})"
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            applied["torch.backends.cudnn.deterministic"] = True
            applied["torch.backends.cudnn.benchmark"] = False
            applied["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

    except ImportError:
        applied["torch"] = "skipped (torch not importable)"

    # ── HF transformers' set_seed (covers Trainer's internal RNG) ───────────
    try:
        import transformers
        transformers.set_seed(per_rank_seed)
        applied["transformers.set_seed"] = per_rank_seed
    except ImportError:
        applied["transformers.set_seed"] = "skipped (transformers not importable)"

    # ── build report ────────────────────────────────────────────────────────
    report = SeedingReport(
        seedhash_input=seedhash_input,
        seedhash_package_version=_seedhash_version(),
        seed_index=seed_index,
        seed_int=base_seed,
        per_rank_seed_int=per_rank_seed,
        rank=rank,
        world_size=world_size,
        local_rank=local_rank,
        local_world_size=local_world_size,
        topology=topology,
        strict=strict,
        applied=applied,
        worker_init_fn=_build_worker_init_fn(per_rank_seed),
        torch_generator=torch_generator,
    )

    if verbose:
        print(
            f"[seeding] topology={topology}  rank={rank}/{world_size}  "
            f"local_rank={local_rank}/{local_world_size}  "
            f"base_seed={base_seed}  per_rank_seed={per_rank_seed}  strict={strict}",
            file=sys.stderr,
        )

    return report


# ---------------------------------------------------------------------------
# CLI — print the deterministic seed sequence for a given seedhash input
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Print the deterministic seed sequence.")
    ap.add_argument(
        "--seedhash-input",
        default=DEFAULT_SEEDHASH_INPUT,
        help="String fed to seedhash. Defaults to the splits' SEEDHASH_INPUT.",
    )
    ap.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N_SEEDS,
        help="How many seeds to draw from the sequence.",
    )
    ap.add_argument(
        "--rank",
        type=int,
        default=None,
        help="If given, also print the per-rank seed for this rank (seed_index=0).",
    )
    args = ap.parse_args()

    print(f"seedhash_input           : {args.seedhash_input!r}")
    print(f"seedhash_package_version : {_seedhash_version()}")
    print(f"n                        : {args.n}")
    seeds = generate_seeds(args.seedhash_input, args.n)
    for i, s in enumerate(seeds):
        print(f"  seed_{i:02d} : {s}")
    if args.rank is not None:
        prs = derive_per_rank_seed(args.seedhash_input, 0, args.rank)
        print(f"per-rank seed (seed_index=0, rank={args.rank}) : {prs}")
