"""Builder for the standalone eval + visualization notebook for r0.

Generates `eval_qwen3_4b_qlora_s00_r0.ipynb` next to this file. Re-runnable.
Cross-platform: discovers REPO at runtime, no hardcoded absolute paths.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().with_name("eval_qwen3_4b_qlora_s00_r0.ipynb")


def md(text: str) -> dict:
    lines = text.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(text: str) -> dict:
    lines = text.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": src,
    }


CELLS: list[dict] = []
C = CELLS.append

# ============================================================================
# Header
# ============================================================================
C(md("""# `qwen3-4b-4bit-qlora-s00-r0` — standalone test eval + visualization

Re-evaluates the tuned model (merged fp16 at `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/gguf/`)
on the seed_00 held-out test split, and visualizes accuracy slices.

This is a separate notebook from the training notebook so you can re-run the eval
without re-training. Outputs go to a `eval_rerun/` subdirectory under the run dir
to avoid clobbering the in-training `test_predictions.jsonl` / `test_metrics.json`.

**Inputs**
- Model: `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/gguf/` (merged bf16 safetensors)
- Test split: `eval/sft/splits/seed_00__351199285/test.jsonl` (464 records)

**Outputs** (under `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/eval_rerun/`)
- `test_predictions.jsonl` — per-record predictions
- `test_metrics.json` — slice tables (type × Bloom × chapter)
- Inline plots — accuracy by type/Bloom/chapter, latency histogram, original-vs-rerun comparison

**Eval methodology** (matches the in-training eval for apples-to-apples comparison)
- Deterministic greedy generation (T=0.0, top_p=1.0)
- Scorable types (MC, TF, Matching): regex extraction → exact match against gold
- Essay/Problem: marked `judge_pending` — LLM-judge step lives in a separate notebook

Container-aware: prefers `/workspace` mount if present, otherwise walks up from cwd.
Runs on Windows, macOS, and Linux without code edits."""))

# ============================================================================
# §1 — Setup
# ============================================================================
C(md("""## §1 — Setup"""))

C(code("""import os, sys, platform, json, time
from pathlib import Path

def _find_repo() -> Path:
    workspace = Path("/workspace")
    if workspace.is_dir() and (workspace / "eval" / "sft" / "splits").is_dir():
        return workspace
    forced = os.environ.get("REPO_ROOT")
    if forced:
        return Path(forced).resolve()
    p = Path.cwd().resolve()
    for d in [p, *p.parents]:
        if (d / ".git").is_dir() or (d / "eval" / "sft" / "splits").is_dir():
            return d
    raise RuntimeError(f"could not find repo root from {p}")

REPO = _find_repo()
print(f"REPO    : {REPO}")
print(f"os      : {platform.system()} {platform.release()}")
print(f"python  : {platform.python_version()}")

import torch
assert torch.cuda.is_available(), "CUDA not visible — launch this notebook inside the NGC container or activate an unsloth env"
dev = torch.cuda.get_device_properties(0)
print(f"gpu     : {dev.name}  ({dev.total_memory/1024**3:.1f} GB, sm_{dev.major}{dev.minor})")
print(f"torch   : {torch.__version__}")"""))

# ============================================================================
# §2 — Configuration
# ============================================================================
C(md("""## §2 — Configuration"""))

C(code("""RUN_ID    = "qwen3-4b-4bit-qlora-s00-r0"
RUN_DIR   = REPO / "models" / "runs" / "dgx_spark" / RUN_ID
MODEL_DIR = RUN_DIR / "gguf"            # merged bf16 safetensors (Unsloth save_pretrained_gguf intermediate)
SEED_DIR  = REPO / "eval" / "sft" / "splits" / "seed_00__351199285"
TEST_JSONL = SEED_DIR / "test.jsonl"

OUT_DIR   = RUN_DIR / "eval_rerun"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PRED_PATH    = OUT_DIR / "test_predictions.jsonl"
METRICS_PATH = OUT_DIR / "test_metrics.json"

# Generation knobs — match the in-training eval for direct comparability
MAX_NEW_TOKENS_SHORT = 32     # MC, TF, Matching
MAX_NEW_TOKENS_LONG  = 512    # Essay/Problem (still generated, just not auto-scored)
TEMPERATURE = 0.0
TOP_P       = 1.0

assert MODEL_DIR.is_dir(),  f"missing merged model dir: {MODEL_DIR}"
assert TEST_JSONL.is_file(), f"missing test split: {TEST_JSONL}"
print(f"MODEL_DIR : {MODEL_DIR}")
print(f"TEST_JSONL: {TEST_JSONL}  ({TEST_JSONL.stat().st_size/1024**2:.1f} MB)")
print(f"OUT_DIR   : {OUT_DIR}")"""))

# ============================================================================
# §3 — Load model
# ============================================================================
C(md("""## §3 — Load tuned model + tokenizer

The `gguf/` directory contains the **merged fp16/bf16 safetensors** that Unsloth
emits as the intermediate step before quantizing to `.gguf`. We load it directly
via `transformers.AutoModelForCausalLM` — no Unsloth needed for inference, and
no separate adapter merge step."""))

C(code("""from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), trust_remote_code=False)
model = AutoModelForCausalLM.from_pretrained(
    str(MODEL_DIR),
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=False,
)
model.eval()
print(f"loaded {model.config.architectures[0]}  dtype={model.dtype}  params={sum(p.numel() for p in model.parameters())/1e9:.2f}B")
print(f"tokenizer: vocab={tokenizer.vocab_size}  pad={tokenizer.pad_token}  eos={tokenizer.eos_token}")"""))

# ============================================================================
# §4 — Load test split
# ============================================================================
C(md("""## §4 — Load test split"""))

C(code("""test_records = []
with TEST_JSONL.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            test_records.append(json.loads(line))

from collections import Counter
type_counts  = Counter(r["meta"]["type"] for r in test_records)
bloom_counts = Counter(r["meta"]["primary_bloom"] for r in test_records)
chap_counts  = Counter(r["meta"]["chapter"] for r in test_records)

print(f"loaded {len(test_records)} test records")
print()
print("by type :", dict(type_counts))
print("by bloom:", dict(sorted(bloom_counts.items())))
print(f"chapters: {sorted(chap_counts)} ({len(chap_counts)} distinct)")"""))

# ============================================================================
# §5 — Generation + extraction helpers
# ============================================================================
C(md("""## §5 — Generation + answer-extraction helpers

Extraction rules mirror what the Spiceland 9e training data actually produces
(verified by scanning `seed_00__351199285/*.jsonl`):

- **MC** → assistant gold is `**A**` … `**E**` (markdown-bold A–E). Extract: first `**[A-E]**`, fall back to first standalone A–E.
- **TF** → assistant gold is `**TRUE**` / `**FALSE**`. Extract: first TRUE/FALSE token.
- **Matching** → assistant gold is a single **letter A–O** (NOT a digit; ~14 distinct letters observed across all splits). Extract: first standalone A–Z. Falls back to a digit only if no letter found (defensive against rubric drift).
- **Essay/Problem** → keep the full generation, mark `judge_pending` (no deterministic auto-score)."""))

C(code("""import re

def extract_predicted(qtype: str, generation: str):
    g = (generation or "").strip()
    if not g:
        return None
    if qtype == "Multiple Choice":
        m = re.search(r"\\*\\*([A-E])\\*\\*", g)
        if m: return m.group(1)
        m = re.search(r"\\b([A-E])\\b", g)
        return m.group(1) if m else None
    if qtype == "True/False":
        if re.search(r"\\b(TRUE|True|true)\\b", g): return "TRUE"
        if re.search(r"\\b(FALSE|False|false)\\b", g): return "FALSE"
        return None
    if qtype == "Matching":
        # Spiceland 9e Matching gold is a single uppercase letter (A-O observed).
        m = re.search(r"\\b([A-Z])\\b", g)
        if m: return m.group(1)
        # Defensive fallback if a rubric ever shipped digit-keyed matching.
        m = re.search(r"\\b(\\d{1,2})\\b", g)
        return m.group(1) if m else None
    return g  # Essay/Problem — keep raw

def gold_for(rec: dict):
    asst = rec["messages"][2]["content"].strip()
    qtype = rec["meta"]["type"]
    if qtype == "Multiple Choice":
        m = re.match(r"^\\*\\*([A-E])\\*\\*", asst)
        return m.group(1) if m else asst[:1]
    if qtype == "True/False":
        m = re.match(r"^\\*\\*(TRUE|FALSE)\\*\\*", asst, re.IGNORECASE)
        return m.group(1).upper() if m else asst.upper().split()[0]
    if qtype == "Matching":
        # Single uppercase letter at the start, e.g. "A", "C", "O".
        m = re.match(r"^([A-Z])\\b", asst)
        return m.group(1) if m else asst[:1]
    return asst

SCORABLE_TYPES = {"Multiple Choice", "True/False", "Matching"}"""))

# ============================================================================
# §6 — Generation loop
# ============================================================================
C(md("""## §6 — Generate predictions

Greedy decoding with `do_sample=False`. Expect ~3-4 min wall clock for 464
records on GB10 (latency dominated by the 117 long-form Essay/Problem records)."""))

C(code("""from tqdm.auto import tqdm

predictions = []
t0 = time.time()

for rec in tqdm(test_records, desc="generating"):
    # Build the prompt = system + user, drop the assistant gold
    messages = [{"role": m["role"], "content": m["content"]} for m in rec["messages"][:2]]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    qtype = rec["meta"]["type"]
    max_new = MAX_NEW_TOKENS_SHORT if qtype in SCORABLE_TYPES else MAX_NEW_TOKENS_LONG

    t_gen = time.time()
    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new,
            do_sample=False,
            temperature=TEMPERATURE if TEMPERATURE > 0 else None,
            top_p=TOP_P if TEMPERATURE > 0 else None,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    latency_ms = (time.time() - t_gen) * 1000.0
    n_in  = inputs["input_ids"].shape[1]
    n_out = out.shape[1] - n_in
    generation = tokenizer.decode(out[0][n_in:], skip_special_tokens=True)

    gold = gold_for(rec)
    pred = extract_predicted(qtype, generation)
    scorable     = qtype in SCORABLE_TYPES
    judge_pending = not scorable
    correct = bool(scorable and gold and pred and gold.strip().upper() == pred.strip().upper())

    predictions.append({
        "question_id"   : rec["meta"]["id"],
        "type"          : qtype,
        "primary_bloom" : rec["meta"]["primary_bloom"],
        "chapter"       : rec["meta"]["chapter"],
        "gold"          : gold,
        "pred"          : pred,
        "correct"       : correct,
        "scorable"      : scorable,
        "judge_pending" : judge_pending,
        "generation"    : generation,
        "n_input_tokens": n_in,
        "n_output_tokens": n_out,
        "latency_ms"    : round(latency_ms, 1),
    })

elapsed = time.time() - t0
print(f"\\ndone in {elapsed:.1f}s  ({elapsed/len(test_records)*1000:.0f} ms/record avg)")

with PRED_PATH.open("w", encoding="utf-8") as fh:
    for p in predictions:
        fh.write(json.dumps(p, ensure_ascii=False) + "\\n")
print(f"wrote {PRED_PATH}  ({len(predictions)} predictions)")"""))

# ============================================================================
# §7 — Aggregate metrics
# ============================================================================
C(md("""## §7 — Aggregate metrics (overall + slices)"""))

C(code("""from collections import defaultdict

def _acc_block():
    return {"correct": 0, "scorable": 0, "judge_pending": 0}

by_type    = defaultdict(_acc_block)
by_bloom   = defaultdict(_acc_block)
by_chapter = defaultdict(_acc_block)
overall    = _acc_block()

for p in predictions:
    blocks = (by_type[p["type"]], by_bloom[p["primary_bloom"]], by_chapter[p["chapter"]], overall)
    for b in blocks:
        if p["judge_pending"]:
            b["judge_pending"] += 1
        else:
            b["scorable"] += 1
            if p["correct"]:
                b["correct"] += 1

def _with_acc(b):
    return {**b, "accuracy": (b["correct"] / b["scorable"]) if b["scorable"] else None}

metrics = {
    "run_id"            : RUN_ID,
    "model_dir"         : str(MODEL_DIR),
    "test_split"        : str(TEST_JSONL),
    "generated_at"      : time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "n_questions"       : len(predictions),
    "n_scorable"        : overall["scorable"],
    "n_judge_pending"   : overall["judge_pending"],
    "overall_accuracy_scorable": round(overall["correct"] / overall["scorable"], 4) if overall["scorable"] else None,
    "by_question_type"  : {k: _with_acc(v) for k, v in by_type.items()},
    "by_primary_bloom"  : {k: _with_acc(v) for k, v in sorted(by_bloom.items())},
    "by_chapter"        : {str(k): _with_acc(v) for k, v in sorted(by_chapter.items())},
    "generation_config" : {
        "max_new_tokens_short": MAX_NEW_TOKENS_SHORT,
        "max_new_tokens_long" : MAX_NEW_TOKENS_LONG,
        "temperature"         : TEMPERATURE,
        "top_p"               : TOP_P,
        "do_sample"           : False,
    },
}
METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(f"wrote {METRICS_PATH}")
print()
print(f"=== overall: {metrics['overall_accuracy_scorable']:.2%}  ({overall['correct']}/{overall['scorable']} scorable, {overall['judge_pending']} judge-pending) ===")
print()
print("by question type:")
for t, v in metrics["by_question_type"].items():
    acc = f"{v['accuracy']:.2%}" if v['accuracy'] is not None else "  —  "
    print(f"  {t:<18s}: {acc}  ({v['correct']}/{v['scorable']} scorable, {v['judge_pending']} judge-pending)")
print()
print("by primary bloom:")
for b, v in metrics["by_primary_bloom"].items():
    acc = f"{v['accuracy']:.2%}" if v['accuracy'] is not None else "  —  "
    print(f"  {b:<12s}: {acc}  ({v['correct']}/{v['scorable']} scorable, {v['judge_pending']} judge-pending)")"""))

# ============================================================================
# §8 — Visualization
# ============================================================================
C(md("""## §8 — Visualization"""))

C(code("""import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["figure.dpi"] = 110
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False"""))

C(md("""### 8.1 — Accuracy by question type"""))

C(code("""types = list(metrics["by_question_type"].keys())
type_acc = [metrics["by_question_type"][t]["accuracy"] or 0.0 for t in types]
type_n   = [metrics["by_question_type"][t]["scorable"]      for t in types]
type_jp  = [metrics["by_question_type"][t]["judge_pending"] for t in types]

fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.bar(types, type_acc, color=["#4C72B0", "#55A868", "#C44E52", "#8172B2"])
for b, n, jp, acc in zip(bars, type_n, type_jp, type_acc):
    label = f"{acc:.1%}\\nn={n}" + (f" (+{jp} pending)" if jp else "")
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01, label, ha="center", va="bottom", fontsize=9)
ax.set_ylim(0, 1.10)
ax.set_ylabel("Accuracy")
ax.set_title(f"{RUN_ID} — accuracy by question type")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
plt.show()"""))

C(md("""### 8.2 — Accuracy by primary Bloom level"""))

C(code("""# Bloom order: pedagogically meaningful (low → high)
BLOOM_ORDER = ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]
blooms = [b for b in BLOOM_ORDER if b in metrics["by_primary_bloom"]]
blooms += [b for b in metrics["by_primary_bloom"] if b not in BLOOM_ORDER]
bloom_acc = [metrics["by_primary_bloom"][b]["accuracy"] or 0.0 for b in blooms]
bloom_n   = [metrics["by_primary_bloom"][b]["scorable"]      for b in blooms]
bloom_jp  = [metrics["by_primary_bloom"][b]["judge_pending"] for b in blooms]

fig, ax = plt.subplots(figsize=(9, 4))
colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(blooms)))
bars = ax.bar(blooms, bloom_acc, color=colors)
for b, n, jp, acc in zip(bars, bloom_n, bloom_jp, bloom_acc):
    label = f"{acc:.1%}\\nn={n}" + (f" (+{jp})" if jp else "")
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01, label, ha="center", va="bottom", fontsize=9)
ax.set_ylim(0, 1.10)
ax.set_ylabel("Accuracy")
ax.set_title(f"{RUN_ID} — accuracy by primary Bloom level")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
plt.show()"""))

C(md("""### 8.3 — Accuracy by chapter"""))

C(code("""chapters = sorted(metrics["by_chapter"].keys(), key=lambda x: int(x))
ch_acc = [metrics["by_chapter"][c]["accuracy"] or 0.0 for c in chapters]
ch_n   = [metrics["by_chapter"][c]["scorable"]      for c in chapters]

fig, ax = plt.subplots(figsize=(14, 4.5))
overall_acc = metrics["overall_accuracy_scorable"] or 0.0
bars = ax.bar(chapters, ch_acc, color=["#55A868" if a >= overall_acc else "#C44E52" for a in ch_acc])
ax.axhline(overall_acc, color="black", linestyle="--", linewidth=1, label=f"overall = {overall_acc:.1%}")
for b, n, acc in zip(bars, ch_n, ch_acc):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01, f"{acc:.0%}\\nn={n}",
            ha="center", va="bottom", fontsize=8)
ax.set_ylim(0, 1.10)
ax.set_xlabel("Chapter")
ax.set_ylabel("Accuracy")
ax.set_title(f"{RUN_ID} — accuracy by chapter (green ≥ overall, red < overall)")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
ax.legend(loc="lower right")
plt.tight_layout()
plt.show()"""))

C(md("""### 8.4 — Latency distribution"""))

C(code("""latencies = [p["latency_ms"] for p in predictions]
lat_by_type = {t: [p["latency_ms"] for p in predictions if p["type"] == t] for t in types}

fig, axes = plt.subplots(1, 2, figsize=(13, 4))

axes[0].hist(latencies, bins=40, color="#4C72B0", edgecolor="white")
axes[0].axvline(np.median(latencies), color="black", linestyle="--", linewidth=1,
                label=f"median={np.median(latencies):.0f} ms")
axes[0].set_xlabel("Latency (ms)")
axes[0].set_ylabel("Count")
axes[0].set_title(f"Per-record generation latency (n={len(latencies)})")
axes[0].legend()

axes[1].boxplot([lat_by_type[t] for t in types], labels=types)
axes[1].set_ylabel("Latency (ms)")
axes[1].set_title("Latency by question type")
axes[1].tick_params(axis="x", rotation=15)

plt.tight_layout()
plt.show()"""))

C(md("""### 8.5 — Rerun vs in-training eval (if the original metrics file is on disk)

Sanity check that the saved merged model reproduces the in-training evaluation
(small differences expected from Unsloth's compiled-kernel path vs vanilla
transformers' generate path)."""))

C(code("""orig_path = RUN_DIR / "test_metrics.json"
if orig_path.exists():
    orig = json.loads(orig_path.read_text(encoding="utf-8"))

    # Compare by question type
    keys = [t for t in types if t in orig.get("by_question_type", {})]
    rerun_acc = [metrics["by_question_type"][k]["accuracy"] or 0.0 for k in keys]
    orig_acc  = [orig["by_question_type"][k].get("accuracy") or 0.0 for k in keys]

    x = np.arange(len(keys))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4))
    b1 = ax.bar(x - w/2, orig_acc,  w, label="in-training eval",  color="#888888")
    b2 = ax.bar(x + w/2, rerun_acc, w, label="rerun (this notebook)", color="#4C72B0")
    for bars, vals in [(b1, orig_acc), (b2, rerun_acc)]:
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01, f"{v:.1%}",
                    ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(keys, rotation=10)
    ax.set_ylabel("Accuracy")
    ax.set_ylim(0, 1.10)
    ax.set_title(f"{RUN_ID} — original vs rerun accuracy")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.legend()
    plt.tight_layout()
    plt.show()

    delta = (metrics["overall_accuracy_scorable"] or 0) - (orig.get("overall_accuracy_scorable") or 0)
    print(f"overall delta vs in-training eval: {delta:+.2%}")
else:
    print(f"no original metrics at {orig_path} — skipping comparison")"""))

# ============================================================================
# Footer
# ============================================================================
C(md("""## Artifacts produced

| Path | What |
|---|---|
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/eval_rerun/test_predictions.jsonl` | per-record predictions (464 rows) |
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/eval_rerun/test_metrics.json` | overall + slice tables (type × Bloom × chapter) |

To score the 117 Essay/Problem items, run an LLM-judge pass (Vera-style) over
`test_predictions.jsonl` — that lives in a separate notebook because it has
different dependencies (judge model + rubric prompts) and a different
operational cadence."""))


nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(CELLS)} cells)")
