"""Generate the r2 recipe notebook by diff-patching r1.

`dsr1-qwen3-8b-4bit-qlora-s00-r2` is the reasoning-prior-ablation successor
to the prepared `qwen3-8b-4bit-qlora-s00-r1` recipe (which is itself the
size-ablation successor to the executed `qwen3-4b-4bit-qlora-s00-r0`
baseline). The three runs form a controlled chain:

    r0  : Qwen3-4B-Instruct-2507   (4B,  vanilla instruct,         executed, 69.2%)
    r1  : Qwen3-8B                  (8B,  hybrid thinking-capable,  prepared)
    r2  : DeepSeek-R1-0528-Qwen3-8B (8B,  R1-distilled reasoning,   prepared)

r1 → r2 swaps ONLY the base model. Same family (Qwen3) → same tokenizer →
same chat template. Same parameter count → same wall-time projection. The
delta is the pretraining lineage: r2's base has been RL-distilled from
DeepSeek-R1 to emit `<think>...</think>` reasoning blocks. r2 still trains
with `enable_thinking=False` (inherited from r1) so the SFT does not damage
the reasoning prior; the question r2 answers is whether that prior survives
non-thinking-mode SFT and remains useful at inference time.

Re-run after editing to regenerate the .ipynb:
    python models/recipes/dgx_spark/_build_r2_notebook.py
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "models" / "recipes" / "dgx_spark" / "qwen3_8b_4bit_qlora_s00_r1.ipynb"
OUT = ROOT / "models" / "recipes" / "dgx_spark" / "dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb"

# ----------------------------------------------------------------------------
# Documented deltas (r1 → r2).
# ----------------------------------------------------------------------------

R2_HEADER = """\
# `dsr1-qwen3-8b-4bit-qlora-s00-r2` — DGX Spark recipe (PREPARED, not executed)

Controlled reasoning-prior-ablation successor to the prepared
`qwen3-8b-4bit-qlora-s00-r1` recipe (which is itself the size-ablation
successor to the executed `qwen3-4b-4bit-qlora-s00-r0` baseline, 69.2% on
the 464-row scorable test split). Same corpus anchor, seed, hyperparameters,
target modules, LoRA rank/alpha, trainer config, **and parameter count**.
Only the base model changes:

    r1 : unsloth/Qwen3-8B                    (hybrid thinking-capable, no RL distill)
    r2 : unsloth/DeepSeek-R1-0528-Qwen3-8B   (R1-distilled reasoning prior on the same backbone)

Same Qwen3 tokenizer → same chat template → same `enable_thinking=False`
training discipline. The only thing that differs is what the base model
brings into SFT: r1 brings a plain pretrained Qwen3, r2 brings a
DeepSeek-R1-style reasoning prior baked in via RL distillation.

Container-aware. Run inside `nvcr.io/nvidia/pytorch:25.11-py3` (launched by
`models/recipes/dgx_spark/launch.sh`). Substrate-of-record: NVIDIA DGX Spark
Unsloth playbook. Hardware notes: `.meta/hardware.md`.

**Why DeepSeek-R1-0528-Qwen3-8B as r2** (Leo, 2026-05-22):
- **Same tokenizer as r0 + r1** — the base is `DeepSeek-R1-0528-Qwen3-8B`,
  i.e. a Qwen3-8B further-trained from R1 distillation. Tokenizer
  vocabulary, chat-template tags (`<|im_start|>`, `<|im_end|>`), and
  `<think>` markers all match the Qwen3 family. No cross-tokenizer
  confound vs r0/r1.
- **Same parameter count as r1** — 8B dense, identical backbone shape, so
  LoRA rank 16 sees the same projection dimensions. The single variable is
  the pretraining lineage. The size question is settled by the r0→r1
  delta; the reasoning-prior question is settled by the r1→r2 delta.
- **Fits comfortably on DGX Spark UMA (119.6 GB)** — same memory profile
  as r1 (~5 GB base 4-bit + activations + optimizer state + LoRA grads).
  The dormant Windows row's 16 GB VRAM is still tight; this recipe is
  intentionally DGX-Spark-targeted.

**Open question r2 is designed to answer**:
Does a reasoning-trained base (DeepSeek-R1 distill) outperform a vanilla
hybrid base (Qwen3-8B) on the Spiceland accounting SFT corpus, even when
both are SFT'd without thinking-mode rendering? If r2 > r1 by a meaningful
margin, the R1 reasoning prior survives non-thinking SFT and is worth the
swap. If r2 ≈ r1, the prior is either damaged by SFT or unhelpful here.

**Decision log** (Leo, 2026-05-22):
- **`enable_thinking=False` at train time, inherited from r1**: The
  Spiceland gold has no `<think>` traces. Training with thinking ON would
  teach r2 to emit empty think blocks and damage the reasoning prior we
  specifically chose this base for. Inference-time thinking remains
  togglable after fine-tuning — that is where r2's prior pays off (or
  doesn't).
- **Synthetic thinking traces explicitly NOT generated**: A more aggressive
  variant would use a teacher model (full DeepSeek-R1, or GPT-4-class) to
  synthesize `<think>` traces for each Spiceland record, then SFT the
  whole `<think>...</think>` + answer sequence. That is r3+ territory:
  expensive, needs a teacher pin, and pollutes the controlled-variable
  chain. r2 is the cheap and rigorous predecessor — same training data
  as r0/r1, only the base model differs.
- **Supersession-note rendering**: still DEFERRED (Diana's split JSONL
  drops `meta.gaap_supersession`). r2 trains on raw Spiceland gold, same
  as r0/r1.
- **Loss weighting 0.85/0.15**: still DEFERRED. Same blocker as r1.
- **r2 launch trigger**: user-gated. Recipe is *prepared*, not *executed*.
  Requires the dormant DGX Spark row to be ACTIVE again. Natural order is
  r1 first (cheaper variable to isolate), then r2 on top."""

R2_SECTION_2_MD = """\
## §2 — Dataset + tokenizer

Diana's splits already carry rendered `messages` (system + user + assistant) per `eval/_format.py`. We map those to a single `text` field via the Qwen3 chat template.

**r2 chat-template handling**: `DeepSeek-R1-0528-Qwen3-8B` inherits the Qwen3 chat template (same `<|im_start|>` / `<|im_end|>` tags). We pass `enable_thinking=False` so the rendered text has no `<think></think>` block — same discipline as r1. The R1 reasoning prior lives in the model weights, not in the trained chat-template surface; preserving it requires not contaminating the assistant turn with synthesized thinking traces. Inference-time thinking remains togglable after fine-tuning, and that is where the prior pays off."""

R2_SECTION_3_MD = """\
## §3 — Base model (4-bit QLoRA via Unsloth `FastModel`)

Playbook-validated path: `FastModel.from_pretrained(load_in_4bit=True, full_finetuning=False)`. Try the Unsloth pre-quantized repo first; on miss, fall back to the official DeepSeek repo and let Unsloth auto-quantize. Same call shape as r0/r1; only the model name changes.

**Note**: `unsloth/DeepSeek-R1-0528-Qwen3-8B` is a Qwen3-8B further-trained with DeepSeek-R1-style reasoning distillation. It uses the Qwen3 backbone, tokenizer, and chat template — so the `train_on_responses_only` masking in §6 still keys on `<|im_start|>user\\n` and `<|im_start|>assistant\\n` exactly as r0/r1 did."""

R2_SECTION_7_MD = """\
## §7 — Train

**Wall-time projection** (inherits r1's projection — same parameter count,
same backbone, same hyperparameters): ~180–200 min wall-clock (3.0–3.3 h)
on this host at the r0-measured 1.933 samples/s scaled for 8B. The R1
distillation does not change the forward-pass FLOPs at the same batch size.
UMA absorbs the extra activation memory; no batch reduction needed.

If throughput drops below 0.8 samples/s, run the playbook page-cache flush
*between* training launches (UMA OOM-recovery):

```
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```"""

R2_SECTION_9_MD = """\
## §9 — Quick eval (50-sample probe)

NOT production eval. Vera's `eval/run.py` is the production path. This is a sanity-check that the adapter generates sensible completions before the user gates a full Vera run. Identical probe protocol to r0 + r1 so the three-way comparison is apples-to-apples.

**r2 delta**: same `enable_thinking=False` on the prompt template as §2 — training-time and inference-time chat-template rendering must match. The probe deliberately does NOT light up the reasoning prior here; that decision is staged for the production Vera run, where it becomes a separate evaluation column (`r2_no_think` vs `r2_with_think`) and can be measured rigorously."""


PATCHES: list[tuple[int, str, str | None, str]] = [

    # Cell 0 — Header markdown: wholesale replacement (r2 framing).
    (0, "header", None, R2_HEADER),

    # Cell 2 — §1 code: bump RUN_ID r1 → r2.
    (
        2,
        "run-id",
        'RUN_ID = "qwen3-8b-4bit-qlora-s00-r1"',
        'RUN_ID = "dsr1-qwen3-8b-4bit-qlora-s00-r2"',
    ),

    # Cell 3 — §2 markdown: r2 reasoning-prior framing.
    (3, "section-2-md", None, R2_SECTION_2_MD),

    # Cell 4 — §2 code: swap base model.
    (
        4,
        "base-model-primary",
        'BASE_MODEL_PRIMARY = "unsloth/Qwen3-8B"',
        'BASE_MODEL_PRIMARY = "unsloth/DeepSeek-R1-0528-Qwen3-8B"',
    ),
    (
        4,
        "base-model-fallback",
        'BASE_MODEL_FALLBACK = "Qwen/Qwen3-8B"',
        'BASE_MODEL_FALLBACK = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"',
    ),
    # Update the inline comment that referenced Qwen3-8B specifically.
    (
        4,
        "render-text-enable-thinking-comment",
        (
            "    # enable_thinking=False: Qwen3-8B is hybrid; the Spiceland gold has\n"
            "    # no <think> traces, so we render in non-thinking mode to preserve\n"
            "    # the thinking prior. See decision log in the header cell."
        ),
        (
            "    # enable_thinking=False: DeepSeek-R1-0528-Qwen3-8B is an R1-distilled\n"
            "    # reasoning model on the Qwen3 backbone. The Spiceland gold has no\n"
            "    # <think> traces; rendering in non-thinking mode preserves the\n"
            "    # reasoning prior we specifically chose this base for. See decision\n"
            "    # log in the header cell."
        ),
    ),

    # Cell 5 — §3 markdown: r2-flavored guard.
    (5, "section-3-md", None, R2_SECTION_3_MD),

    # Cell 13 — §7 markdown: r2 wall-time projection (inherits r1's).
    (13, "section-7-md", None, R2_SECTION_7_MD),

    # Cell 16 — §8 code: rewrite the embedded notes from r1 → r2.
    (
        16,
        "manifest-loss-weighting-note",
        (
            '"loss_weighting_note": (\n'
            '            "r1 inherits r0\'s uniform loss weighting. Pat\'s 0.85/0.15 gold/supersession "\n'
            '            "weighting still deferred (no SFTTrainer support; needs custom collator + "\n'
            '            "supersession block plumbed into split records)."\n'
            "        ),"
        ),
        (
            '"loss_weighting_note": (\n'
            '            "r2 inherits r0/r1\'s uniform loss weighting. Pat\'s 0.85/0.15 gold/supersession "\n'
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
            '            "r1 trains on raw Spiceland gold, same as r0. eval/_format.py does not render "\n'
            '            "meta.gaap_supersession into the assistant turn, and Diana\'s split JSONL drops "\n'
            '            "the field. Deferred to r2+ (needs split re-emission with a new sha)."\n'
            "        ),"
        ),
        (
            '"supersession_note": (\n'
            '            "r2 trains on raw Spiceland gold, same as r0 + r1. eval/_format.py does not "\n'
            '            "render meta.gaap_supersession into the assistant turn, and Diana\'s split "\n'
            '            "JSONL drops the field. Deferred to r3+ (needs split re-emission with a new sha)."\n'
            "        ),"
        ),
    ),

    # Cell 17 — §9 markdown: r2 reasoning-prior framing.
    (17, "section-9-md", None, R2_SECTION_9_MD),
]


def _cell_source(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _set_cell_source(cell: dict, text: str) -> None:
    lines = text.split("\n")
    out = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    cell["source"] = out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"source not found: {SRC}\n"
            "Run `python models/recipes/dgx_spark/_build_r1_notebook.py` first."
        )
    nb = json.loads(SRC.read_text(encoding="utf-8"))

    for idx, label, old, new in PATCHES:
        cell = nb["cells"][idx]
        current = _cell_source(cell)
        if old is None:
            _set_cell_source(cell, new)
            print(f"  [cell {idx:2}] {label:36s}  REPLACED ({len(current)} -> {len(new)} chars)")
            continue
        if old not in current:
            raise SystemExit(
                f"patch failed at cell {idx} ({label}): substring not found.\n"
                f"  looking for: {old[:160]!r}...\n"
                f"  current src (first 320 chars): {current[:320]!r}..."
            )
        replaced = current.replace(old, new, 1)
        _set_cell_source(cell, replaced)
        print(f"  [cell {idx:2}] {label:36s}  PATCHED")

    # Strip stale outputs (r1 already had them stripped, but be defensive).
    cleared = 0
    for cell in nb["cells"]:
        if cell.get("cell_type") == "code":
            if cell.get("outputs") or cell.get("execution_count") is not None:
                cell["outputs"] = []
                cell["execution_count"] = None
                cleared += 1
            cell.setdefault("id", uuid.uuid4().hex[:12])

    print(f"  cleared outputs from {cleared} code cells")
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()
