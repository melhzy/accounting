"""Generate the r1 recipe notebook by diff-patching r0.

`qwen3-8b-4bit-qlora-s00-r1` is the controlled-size-ablation successor to the
executed `qwen3-4b-4bit-qlora-s00-r0` baseline (see ROADMAP §3 item #5). The
two runs share corpus anchor, seed, hyperparameters, target modules, LoRA
rank/alpha, and trainer config. Only the base model changes (Qwen3-4B-Instruct-2507
→ Qwen3-8B). This script encodes that delta explicitly so the diff is reviewable.

Re-run after editing to regenerate the .ipynb:
    python models/recipes/dgx_spark/_build_r1_notebook.py
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "models" / "recipes" / "dgx_spark" / "qwen3_4b_4bit_qlora_s00_r0.ipynb"
OUT = ROOT / "models" / "recipes" / "dgx_spark" / "qwen3_8b_4bit_qlora_s00_r1.ipynb"

# ----------------------------------------------------------------------------
# Documented deltas (r0 → r1). Each entry is (cell_index, old_substring, new_substring).
# A `None` old_substring means the cell source is replaced wholesale with `new_substring`.
# Cell indexing mirrors the r0 layout enumerated in `_build_r1_notebook.py` header.
# ----------------------------------------------------------------------------

R1_HEADER = """\
# `qwen3-8b-4bit-qlora-s00-r1` — DGX Spark recipe (PREPARED, not executed)

Controlled size-ablation successor to the executed `qwen3-4b-4bit-qlora-s00-r0`
baseline (69.2% on the 464-row scorable test split). Same corpus anchor, seed,
hyperparameters, target modules, LoRA rank/alpha, and trainer config. Only the
base model changes: `unsloth/Qwen3-4B-Instruct-2507` → `unsloth/Qwen3-8B`.

Container-aware. Run inside `nvcr.io/nvidia/pytorch:25.11-py3` (launched by
`models/recipes/dgx_spark/launch.sh`). Substrate-of-record: NVIDIA DGX Spark
Unsloth playbook. Hardware notes: `.meta/hardware.md`.

**Why Qwen3-8B as r1** (Leo, 2026-05-21):
- **Same family/tokenizer as r0** — Qwen3 lineage means the comparison isolates
  the size variable. A jump to a different family (Llama-3.1-8B, Mistral-7B,
  DeepSeek-distill) would confound size with tokenizer + pretraining mix.
- **Fits comfortably on DGX Spark UMA (119.6 GB)** — 8B 4-bit base ~5 GB +
  activations + optimizer state + LoRA grads = comfortable. The dormant Windows
  row's 16 GB VRAM is tight for 8B even at 4-bit, so this recipe is intentionally
  DGX-Spark-targeted (§3 item #5: "Deferred — needs DGX Spark ACTIVE").
- **Thinking capability preserved, not trained** — Qwen3-8B is hybrid
  (instruct + thinking via chat template). The Spiceland gold has no `<think>`
  traces; training with thinking ON would teach the model to emit empty think
  blocks and damage the prior. We render the chat template with
  `enable_thinking=False`, leaving the thinking weights pristine for downstream
  inference-time use. The size ablation is clean against r0 (which was
  Instruct-2507, no thinking mode).

**Decision log** (Leo, 2026-05-21):
- **Supersession-note rendering**: STILL DEFERRED (was r1 target; pushed to r2+).
  Diana's split JSONL drops `meta.gaap_supersession` and `eval/_format.py` does
  not template-render it into the assistant turn. r1 trains on raw Spiceland
  gold, same as r0. Resolving this requires re-emitting splits with a new sha.
- **Loss weighting 0.85/0.15**: STILL DEFERRED. SFTTrainer does not support
  per-segment loss weighting; a custom collator emitting per-token weights is
  required. Gated on the supersession block being plumbed into split records.
- **Reasoning-prior ablation (r2 target)**: replace Qwen3-8B with
  `unsloth/DeepSeek-R1-0528-Qwen3-8B`. Same tokenizer, same parameter count,
  swap-in reasoning prior. Isolates "thinking prior" against this r1's "plain
  Qwen3-8B" baseline. Separate run id.
- **r1 launch trigger**: user-gated. Recipe is *prepared*, not *executed*.
  Requires the dormant DGX Spark row to be ACTIVE again."""

R1_CELL_1_HEADER = """\
## §1 — Substrate guardrails

Fail fast if we are on the wrong host, wrong CUDA arch, wrong split version, or the seed split sha drifted from `eval/sft/splits/manifest.json`. Then apply project-wide deterministic seeding via `eval/seeding.py` (see the seeding-policy memory: `seedhash` is the sole seed-derivation mechanism, covering CPU + single-GPU + multi-GPU one-host + multi-host). Same guardrails as r0 — only the `RUN_ID` differs; the seeding call is new (r0 relied implicitly on `SFTConfig(seed=...)`)."""

R1_CELL_3_HEADER = """\
## §2 — Dataset + tokenizer

Diana's splits already carry rendered `messages` (system + user + assistant) per `eval/_format.py`. We map those to a single `text` field via the Qwen3 chat template.

**r1 delta from r0**: Qwen3-8B (original, not the 2507 Instruct line) is a hybrid thinking model. We pass `enable_thinking=False` to `apply_chat_template` so the rendered text has no `<think></think>` block. The gold answers carry no thinking traces; training with thinking ON would damage the thinking prior. Inference-time thinking remains togglable after fine-tuning."""

R1_CELL_5_HEADER = """\
## §3 — Base model (4-bit QLoRA via Unsloth `FastModel`)

Playbook-validated path: `FastModel.from_pretrained(load_in_4bit=True, full_finetuning=False)`. Try the Unsloth pre-quantized repo first; on miss, fall back to the official Qwen repo and let Unsloth auto-quantize. Same call shape as r0; only the model name changes."""

R1_CELL_7_HEADER = """\
## §4 — LoRA adapter

Same rank/alpha/target-modules as r0 — the ablation against r0 must keep the adapter shape constant so the only delta is base-model size. Trainable-param count will scale with the 8B base hidden size."""

R1_CELL_9_HEADER = """\
## §5 — SFTTrainer config

Identical to r0 (per-device batch 2 × grad-accum 4 → effective 8; 3 epochs; cosine LR with 5% warmup; `adamw_8bit`; `eval_steps=110` for ≈12 dev-loss readings + EarlyStopping patience=3). The size ablation requires every knob below the base model to stay constant."""

R1_CELL_13_HEADER = """\
## §7 — Train

**Wall-time projection** (r0 actuals → r1 estimate): r0 trained at 1.933 samples/s on this host (full real-world rate, including eval + checkpoint I/O), taking 91.5 min for 3,537 train rows × 3 epochs. Qwen3-8B has ~2× the active parameters per forward pass at the same batch size; expect ~0.95–1.05 samples/s and **~180–200 min wall-clock** (3.0–3.3 h). The UMA pool absorbs the extra activation memory; no batch reduction needed.

If throughput drops below 0.8 samples/s, run the playbook page-cache flush *between* training launches (UMA OOM-recovery):

```
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```"""

R1_CELL_15_HEADER = """\
## §8 — Manifest emission

Per Leo's standing rule — every run pinned. The `source_jsonl_sha256` binds this adapter to `spiceland9e-v1.1.0`, identical to r0; the cross-run delta is recoverable from the `recipe.base_model` field."""

R1_CELL_17_HEADER = """\
## §9 — Quick eval (50-sample probe)

NOT production eval. Vera's `eval/run.py` is the production path. This is a sanity-check that the adapter generates sensible completions before the user gates a full Vera run. Identical probe protocol to r0 so the side-by-side comparison is apples-to-apples.

**r1 delta**: same `enable_thinking=False` on the prompt template as §2 — training-time and inference-time chat-template rendering must match or the model will see a token distribution it was never trained on."""

R1_CELL_19_HEADER = """\
## §10 — GGUF export (optional, gated)

For Ollama / llama.cpp portability. Default OFF for r1 (this is a prepared-not-executed stub); flip to True after a Vera PASS on the adapter."""


# Exact-substring patches keyed by (cell_index, label).
PATCHES: list[tuple[int, str, str | None, str]] = [
    # (cell_index, label, old_substring_or_None, new_substring)

    # Cell 0 — Header markdown: wholesale replacement.
    (0, "header", None, R1_HEADER),

    # Cell 1 — §1 markdown: minor tweak to call out the only delta is RUN_ID.
    (1, "section-1-md", None, R1_CELL_1_HEADER),

    # Cell 2 — §1 code: bump RUN_ID + append `seed_everything` invocation.
    (
        2,
        "run-id",
        'RUN_ID = "qwen3-4b-4bit-qlora-s00-r0"',
        'RUN_ID = "qwen3-8b-4bit-qlora-s00-r1"',
    ),
    (
        2,
        "seed-everything",
        'print(f"counts: {seed00[\'split_counts\']}")',
        (
            'print(f"counts: {seed00[\'split_counts\']}")\n'
            '\n'
            '# ── Deterministic seeding (project policy: seedhash is the sole derivation\n'
            '# mechanism; eval/seeding.py covers CPU + single-GPU + multi-GPU one-host +\n'
            '# multi-host topologies). Embed the report in manifest.json for replay.\n'
            'sys.path.insert(0, str(REPO / "eval"))\n'
            'from seeding import seed_everything  # noqa: E402\n'
            'SEEDING_REPORT = seed_everything(seed_int=351199285)\n'
            'print(f"seeding: topology={SEEDING_REPORT.topology} "\n'
            '      f"rank={SEEDING_REPORT.rank}/{SEEDING_REPORT.world_size} "\n'
            '      f"per_rank_seed={SEEDING_REPORT.per_rank_seed_int} "\n'
            '      f"strict={SEEDING_REPORT.strict}")'
        ),
    ),

    # Cell 3 — §2 markdown: explain enable_thinking=False.
    (3, "section-2-md", None, R1_CELL_3_HEADER),

    # Cell 4 — §2 code: swap base model + add enable_thinking=False.
    (
        4,
        "base-model-primary",
        'BASE_MODEL_PRIMARY = "unsloth/Qwen3-4B-Instruct-2507"',
        'BASE_MODEL_PRIMARY = "unsloth/Qwen3-8B"',
    ),
    (
        4,
        "base-model-fallback",
        'BASE_MODEL_FALLBACK = "Qwen/Qwen3-4B-Instruct-2507"',
        'BASE_MODEL_FALLBACK = "Qwen/Qwen3-8B"',
    ),
    (
        4,
        "render-text-enable-thinking",
        (
            "    return tok_probe.apply_chat_template(\n"
            "        rec[\"messages\"], tokenize=False, add_generation_prompt=False\n"
            "    )"
        ),
        (
            "    # enable_thinking=False: Qwen3-8B is hybrid; the Spiceland gold has\n"
            "    # no <think> traces, so we render in non-thinking mode to preserve\n"
            "    # the thinking prior. See decision log in the header cell.\n"
            "    return tok_probe.apply_chat_template(\n"
            "        rec[\"messages\"], tokenize=False, add_generation_prompt=False,\n"
            "        enable_thinking=False,\n"
            "    )"
        ),
    ),

    # Cell 5 — §3 markdown: minor pointer; substantive guardrail is in r0's text.
    (5, "section-3-md", None, R1_CELL_5_HEADER),

    # Cell 7 — §4 markdown: clarify constant-shape adapter.
    (7, "section-4-md", None, R1_CELL_7_HEADER),

    # Cell 9 — §5 markdown: emphasize "identical to r0".
    (9, "section-5-md", None, R1_CELL_9_HEADER),

    # Cell 13 — §7 markdown: update wall-time projection from r0 actuals.
    (13, "section-7-md", None, R1_CELL_13_HEADER),

    # Cell 15 — §8 markdown: r1 wording.
    (15, "section-8-md", None, R1_CELL_15_HEADER),

    # Cell 16 — §8 code: embed the seeding report into manifest.json and
    # update the inline notes so it doesn't claim "r0" when written by r1.
    (
        16,
        "manifest-seeding-report",
        '"seed_int": SEED,',
        '"seed_int": SEED,\n        "seeding_report": SEEDING_REPORT.to_dict(),',
    ),
    (
        16,
        "manifest-loss-weighting-note",
        (
            '"loss_weighting_note": (\n'
            '            "r0 trains uniformly. Pat\'s 0.85/0.15 gold/supersession weighting deferred to r1; "\n'
            '            "requires custom collator + supersession block plumbed into split records."\n'
            "        ),"
        ),
        (
            '"loss_weighting_note": (\n'
            '            "r1 inherits r0\'s uniform loss weighting. Pat\'s 0.85/0.15 gold/supersession "\n'
            '            "weighting still deferred (no SFTTrainer support; needs custom collator + "\n'
            '            "supersession block plumbed into split records)."\n'
            "        ),"
        ),
    ),
    (
        16,
        "manifest-supersession-note",
        (
            '"supersession_note": (\n'
            '            "r0 trains on raw Spiceland gold. eval/_format.py does not render "\n'
            '            "meta.gaap_supersession into the assistant turn, and Diana\'s split JSONL drops "\n'
            '            "the field. Deferred to r1."\n'
            "        ),"
        ),
        (
            '"supersession_note": (\n'
            '            "r1 trains on raw Spiceland gold, same as r0. eval/_format.py does not render "\n'
            '            "meta.gaap_supersession into the assistant turn, and Diana\'s split JSONL drops "\n'
            '            "the field. Deferred to r2+ (needs split re-emission with a new sha)."\n'
            "        ),"
        ),
    ),

    # Cell 17 — §9 markdown: explain enable_thinking=False in the probe.
    (17, "section-9-md", None, R1_CELL_17_HEADER),

    # Cell 18 — §9 code: add enable_thinking=False to the probe prompt render
    # so train-time and inference-time renderings match.
    (
        18,
        "probe-enable-thinking",
        (
            "        prompt_text = tokenizer.apply_chat_template(\n"
            "            msgs, tokenize=False, add_generation_prompt=True\n"
            "        )"
        ),
        (
            "        prompt_text = tokenizer.apply_chat_template(\n"
            "            msgs, tokenize=False, add_generation_prompt=True,\n"
            "            enable_thinking=False,\n"
            "        )"
        ),
    ),

    # Cell 19 — §10 markdown: r1 wording, default OFF.
    (19, "section-10-md", None, R1_CELL_19_HEADER),

    # Cell 20 — §10 code: default the flag to False for the stub.
    (
        20,
        "gguf-flag-default",
        "do_gguf_export = True",
        "do_gguf_export = False",
    ),
]


def _cell_source(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _set_cell_source(cell: dict, text: str) -> None:
    lines = text.split("\n")
    # nbformat convention: each list element is a line including its trailing \n,
    # except the last element which has no trailing \n.
    out = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    cell["source"] = out


def main() -> None:
    nb = json.loads(SRC.read_text(encoding="utf-8"))

    for idx, label, old, new in PATCHES:
        cell = nb["cells"][idx]
        current = _cell_source(cell)
        if old is None:
            _set_cell_source(cell, new)
            print(f"  [cell {idx:2}] {label:32s}  REPLACED ({len(current)} -> {len(new)} chars)")
            continue
        if old not in current:
            raise SystemExit(
                f"patch failed at cell {idx} ({label}): substring not found.\n"
                f"  looking for: {old[:120]!r}...\n"
                f"  current src (first 240 chars): {current[:240]!r}..."
            )
        replaced = current.replace(old, new, 1)
        _set_cell_source(cell, replaced)
        print(f"  [cell {idx:2}] {label:32s}  PATCHED")

    # Strip stale outputs and execution_count from every code cell so the
    # committed r1 .ipynb is a clean stub. Re-running inside the container
    # will repopulate these.
    cleared = 0
    for cell in nb["cells"]:
        if cell.get("cell_type") == "code":
            if cell.get("outputs") or cell.get("execution_count") is not None:
                cell["outputs"] = []
                cell["execution_count"] = None
                cleared += 1
            # Re-id any code cells that lost their id (rare; defensive).
            cell.setdefault("id", uuid.uuid4().hex[:12])

    print(f"  cleared outputs from {cleared} code cells")
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()
