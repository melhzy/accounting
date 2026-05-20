"""Generate the first-seed bf16-LoRA training notebook.

Adapted from `.code_base/notebooks/qwen/Qwen3_(4B)-Instruct.py` (Unsloth's
canonical Qwen3-4B-Instruct SFT pattern). Key deltas from the upstream:

  - bf16-LoRA, not 4-bit (load_in_4bit=False)
  - r=16, alpha=32  (Leo's spec; upstream uses r=32)
  - Custom data path → eval/sft/splits/seed_00__351199285/{train,valid,test}
  - num_train_epochs=3 (not max_steps=60)
  - eval_strategy=steps + EarlyStoppingCallback on eval_loss
  - cosine LR schedule with 5% warmup
  - Post-training evaluation on the held-out test split
  - Manifest sidecar per Leo's spec
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "models" / "recipes" / "qwen3_4b_seed00_bf16_lora.ipynb"
OUT.parent.mkdir(parents=True, exist_ok=True)


def md(text: str) -> dict:
    """Markdown cell."""
    lines = text.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(text: str) -> dict:
    """Code cell."""
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
C(md("""# Qwen3-4B-Instruct · bf16-LoRA · seed_00 · Windows

Fine-tune Qwen3-4B-Instruct on the Spiceland 9e accounting test bank using
**bf16 LoRA** (r=16, alpha=32), seed_00 split from `eval/sft/splits/`.

- **Train + Valid**: `seed_00__351199285/{train,valid}.jsonl` — used by the trainer.
- **Test**: `seed_00__351199285/test.jsonl` — held out until after training, evaluated in the last cells.

Adapted from `.code_base/notebooks/qwen/Qwen3_(4B)-Instruct.py` (Unsloth's canonical pattern).
Key differences from upstream: bf16 not 4-bit, r=16 not r=32, 3 epochs not max_steps=60,
custom data path, train_on_responses_only for completion-only loss masking, post-training
eval on the held-out test split.

### Windows-specific adjustments

- `dataloader_num_workers=0` — Windows uses spawn (not fork) for multiprocess data loaders; subprocess pickling chokes in Jupyter. Single-process loading is bulletproof and the throughput cost is negligible for this workload.
- `HF_HOME` set to `D:\\hf_cache` so the ~4 GB Qwen3-4B base download lands on the larger free-space drive (`D:` has 167 GB free vs `C:` 105 GB).
- **vLLM is OFF the serving menu on Windows** (no native `vllm._C` extension). Adapter export goes to **GGUF (llama.cpp / Ollama)** or stays in **Unsloth-native inference** — see the final cells.
- Triton emits non-fatal warnings about `cuobjdump.exe` / `nvdisasm.exe` not found at first import. These are debug binaries; the runtime kernels are unaffected. Ignore."""))

# ============================================================================
# Setup
# ============================================================================
C(md("""## 1. Setup

Verify the env is the `unsloth` conda env on Python 3.12 with a CUDA-visible GPU.
Also sets `HF_HOME` to the larger drive **before** importing anything that touches HuggingFace,
and asserts vLLM is NOT installed (it breaks unsloth import on Windows — see notebook header)."""))

C(code("""import os
# Pin the HuggingFace cache to D:\\ (larger free-space drive) — must be set BEFORE
# importing transformers / datasets / unsloth.
os.environ.setdefault("HF_HOME", r"D:\\hf_cache")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")  # faster model downloads

import sys, platform, importlib.util
import torch

print("python      :", platform.python_version())
print("executable  :", sys.executable)
print("HF_HOME     :", os.environ["HF_HOME"])
print("torch       :", torch.__version__)
print("cuda_avail  :", torch.cuda.is_available())
assert torch.cuda.is_available(), "No CUDA GPU visible — activate the unsloth conda env first."
p = torch.cuda.get_device_properties(0)
print(f"gpu         : {p.name}  ({p.total_memory/1024**3:.1f} GB, sm_{p.major}{p.minor})")

# Windows guardrail: vllm 0.21.0 installs on Windows but ships no native C ext,
# and unsloth_zoo's vllm_utils.py blindly imports vllm.model_executor — which then
# blows up with `No module named 'vllm._C'`. Uninstall vllm before training.
assert importlib.util.find_spec("vllm") is None, \\
    "vllm is installed and will break `import unsloth` on Windows. " \\
    "Run: pip uninstall vllm -y"

import unsloth, transformers, peft, trl, datasets, accelerate
print()
print(f"unsloth     : {unsloth.__version__}")
print(f"transformers: {transformers.__version__}")
print(f"peft        : {peft.__version__}")
print(f"trl         : {trl.__version__}")
print(f"datasets    : {datasets.__version__}")
print(f"accelerate  : {accelerate.__version__}")"""))

# ============================================================================
# Configuration
# ============================================================================
C(md("""## 2. Configuration

All knobs live here so the rest of the notebook is run-as-is."""))

C(code("""from pathlib import Path

# ---- Paths --------------------------------------------------------------
REPO_ROOT = Path(r"D:\\Github\\accounting")
SEED_DIR  = REPO_ROOT / "eval" / "sft" / "splits" / "seed_00__351199285"
TRAIN_JSONL = SEED_DIR / "train.jsonl"
VALID_JSONL = SEED_DIR / "valid.jsonl"
TEST_JSONL  = SEED_DIR / "test.jsonl"
assert TRAIN_JSONL.exists() and VALID_JSONL.exists() and TEST_JSONL.exists(), \\
    f"missing split files under {SEED_DIR}"

RUN_ID  = "qwen3_4b_seed00_bf16_lora"
RUN_DIR = REPO_ROOT / "models" / "runs" / RUN_ID
RUN_DIR.mkdir(parents=True, exist_ok=True)

# ---- Model -------------------------------------------------------------
BASE_MODEL      = "unsloth/Qwen3-4B-Instruct-2507"  # Leo's pick; sm_89-compatible
MAX_SEQ_LENGTH  = 2048                               # p95=605, only 1 record (max=2310) truncates
LOAD_IN_4BIT    = False                              # bf16 LoRA (user's choice)
LOAD_IN_8BIT    = False
FULL_FINETUNING = False                              # LoRA, not full FT

# ---- LoRA -------------------------------------------------------------
LORA_R         = 16   # Leo's recommended default
LORA_ALPHA     = 32   # 2 * r
LORA_DROPOUT   = 0
LORA_TARGETS   = ["q_proj","k_proj","v_proj","o_proj",
                  "gate_proj","up_proj","down_proj"]
RANDOM_SEED    = 351199285   # seed_00's seed_int (deterministic with the split)

# ---- Training ---------------------------------------------------------
NUM_EPOCHS                 = 3
LEARNING_RATE              = 2e-4
PER_DEVICE_BATCH_SIZE      = 2
GRAD_ACCUM_STEPS           = 8        # effective batch 16
WARMUP_RATIO               = 0.05
WEIGHT_DECAY               = 0.001
LR_SCHEDULER               = "cosine"
OPTIM                      = "adamw_8bit"  # 8-bit Adam saves VRAM
EVAL_STEPS                 = 50
SAVE_STEPS                 = 50
SAVE_TOTAL_LIMIT           = 3
EARLY_STOPPING_PATIENCE    = 3

print(f"RUN_ID:       {RUN_ID}")
print(f"RUN_DIR:      {RUN_DIR}")
print(f"BASE_MODEL:   {BASE_MODEL}")
print(f"LORA:         r={LORA_R}, alpha={LORA_ALPHA}, targets={LORA_TARGETS}")
print(f"TRAIN:        {NUM_EPOCHS} epochs, LR={LEARNING_RATE}, eff_batch={PER_DEVICE_BATCH_SIZE * GRAD_ACCUM_STEPS}")"""))

# ============================================================================
# Load base model
# ============================================================================
C(md("""## 3. Load Qwen3-4B-Instruct (bf16)

`load_in_4bit=False` means we load the full bf16 weights — ~8 GB VRAM for the base
plus activations during training. On 16 GB cards this is tight but fits when
gradient checkpointing is on (which it is by default below)."""))

C(code("""from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name      = BASE_MODEL,
    max_seq_length  = MAX_SEQ_LENGTH,
    load_in_4bit    = LOAD_IN_4BIT,
    load_in_8bit    = LOAD_IN_8BIT,
    full_finetuning = FULL_FINETUNING,
)
print("base model loaded.")"""))

# ============================================================================
# LoRA
# ============================================================================
C(md("""## 4. Attach LoRA adapters

`use_gradient_checkpointing="unsloth"` is the memory-efficient variant
(~30% less VRAM than vanilla). Required for bf16 LoRA on a 16 GB card."""))

C(code("""model = FastLanguageModel.get_peft_model(
    model,
    r                          = LORA_R,
    target_modules             = LORA_TARGETS,
    lora_alpha                 = LORA_ALPHA,
    lora_dropout               = LORA_DROPOUT,
    bias                       = "none",
    use_gradient_checkpointing = "unsloth",
    random_state               = RANDOM_SEED,
    use_rslora                 = False,
    loftq_config               = None,
)
print("LoRA adapters attached.")"""))

# ============================================================================
# Data
# ============================================================================
C(md("""## 5. Load + tokenize the data

The JSONL records already have `messages = [{role: system|user|assistant, content: ...}]`
in chat-template form. We attach Qwen3's chat template via `get_chat_template`, then map
each record to a single rendered `text` field that `SFTTrainer` consumes via
`dataset_text_field="text"`."""))

C(code("""from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(tokenizer, chat_template="qwen3-instruct")

raw = load_dataset("json", data_files={
    "train": str(TRAIN_JSONL),
    "valid": str(VALID_JSONL),
    "test":  str(TEST_JSONL),
})
print({k: len(v) for k, v in raw.items()})"""))

C(code("""def formatting_prompts_func(examples):
    convos = examples["messages"]
    texts = [
        tokenizer.apply_chat_template(c, tokenize=False, add_generation_prompt=False)
        for c in convos
    ]
    return {"text": texts}

dataset = raw.map(formatting_prompts_func, batched=True, remove_columns=raw["train"].column_names)
print("rendered text columns ready.")"""))

# ============================================================================
# Sanity check
# ============================================================================
C(md("""## 6. Sanity check — one rendered training example"""))

C(code("""print(dataset["train"][0]["text"][:2000])
print()
print("--- truncated; total chars =", len(dataset["train"][0]["text"]))"""))

# ============================================================================
# Trainer
# ============================================================================
C(md("""## 7. Configure the trainer

Three behaviors stacked on top of the upstream pattern:
- **Validation during training** (`eval_strategy="steps"`, eval every 50 steps) using the
  seed_00 valid split. Used for early-stopping on `eval_loss`.
- **Save best checkpoint by eval_loss** so we can roll back if late epochs overfit.
- **Completion-only loss** (applied in the next cell via `train_on_responses_only`)."""))

C(code("""from trl import SFTTrainer, SFTConfig
from transformers import EarlyStoppingCallback

trainer = SFTTrainer(
    model         = model,
    tokenizer     = tokenizer,
    train_dataset = dataset["train"],
    eval_dataset  = dataset["valid"],
    args = SFTConfig(
        dataset_text_field          = "text",
        per_device_train_batch_size = PER_DEVICE_BATCH_SIZE,
        gradient_accumulation_steps = GRAD_ACCUM_STEPS,
        num_train_epochs            = NUM_EPOCHS,
        learning_rate               = LEARNING_RATE,
        warmup_ratio                = WARMUP_RATIO,
        weight_decay                = WEIGHT_DECAY,
        lr_scheduler_type           = LR_SCHEDULER,
        optim                       = OPTIM,
        seed                        = RANDOM_SEED,

        # bf16 on Ada (sm_89)
        bf16 = True,
        fp16 = False,

        # evaluation + early stopping
        eval_strategy              = "steps",
        eval_steps                 = EVAL_STEPS,
        save_strategy              = "steps",
        save_steps                 = SAVE_STEPS,
        save_total_limit           = SAVE_TOTAL_LIMIT,
        load_best_model_at_end     = True,
        metric_for_best_model      = "eval_loss",
        greater_is_better          = False,

        # logging + io
        logging_steps     = 10,
        output_dir        = str(RUN_DIR / "checkpoints"),
        report_to         = "none",
        # Windows: keep dataloader single-process. PyTorch on Windows uses spawn
        # for num_workers>0, which re-imports the notebook module and chokes
        # in Jupyter. Throughput cost is negligible for this dataset size.
        dataloader_num_workers = 0,
    ),
)
trainer.add_callback(EarlyStoppingCallback(early_stopping_patience=EARLY_STOPPING_PATIENCE))
print("trainer ready.")"""))

# ============================================================================
# Completion-only masking
# ============================================================================
C(md("""## 8. Apply completion-only loss masking

`train_on_responses_only` masks the user + system tokens so loss is computed only on
the assistant's response tokens. This is the key knob that lets stub TF/Matching
records coexist with worked-solution records in one run without the model
overfitting to "always emit a single letter / number"."""))

C(code("""from unsloth.chat_templates import train_on_responses_only

trainer = train_on_responses_only(
    trainer,
    instruction_part = "<|im_start|>user\\n",
    response_part    = "<|im_start|>assistant\\n",
)

# Verify the mask — print one example showing only the response tokens
import re
sample = trainer.train_dataset[0]
decoded = tokenizer.decode(
    [tokenizer.pad_token_id if x == -100 else x for x in sample["labels"]]
).replace(tokenizer.pad_token, " ")
# Compact runs of spaces from masked-out tokens
print(re.sub(r" {3,}", "  …  ", decoded)[:800])"""))

# ============================================================================
# Memory snapshot
# ============================================================================
C(md("""## 9. Pre-training VRAM snapshot"""))

C(code("""gpu = torch.cuda.get_device_properties(0)
start_mem = round(torch.cuda.max_memory_reserved() / 1024**3, 2)
print(f"GPU            : {gpu.name}  ({gpu.total_memory/1024**3:.1f} GB total)")
print(f"Reserved before: {start_mem} GB")"""))

# ============================================================================
# Train
# ============================================================================
C(md("""## 10. Train

Expected wall-time on RTX 4090 Laptop (16 GB): ~35-60 min for 3 epochs on 3,537
records with effective batch 16. Watch the `eval_loss` column for early-stopping;
the best checkpoint is auto-restored at the end."""))

C(code("""trainer_stats = trainer.train()"""))

# ============================================================================
# Post-training
# ============================================================================
C(md("""## 11. Save adapter + post-training stats + manifest"""))

C(code("""import hashlib, json, time

end_mem  = round(torch.cuda.max_memory_reserved() / 1024**3, 2)
peak_lora_mem = round(end_mem - start_mem, 2)
runtime  = trainer_stats.metrics["train_runtime"]
print(f"runtime         : {runtime:.1f}s  ({runtime/60:.1f} min)")
print(f"peak VRAM       : {end_mem} GB  (+{peak_lora_mem} GB for LoRA training)")
print(f"peak VRAM pct   : {end_mem / (gpu.total_memory/1024**3) * 100:.1f}%")

# Save the LoRA adapter + tokenizer
ADAPTER_DIR = RUN_DIR / "adapter"
model.save_pretrained(str(ADAPTER_DIR))
tokenizer.save_pretrained(str(ADAPTER_DIR))
print(f"adapter saved   : {ADAPTER_DIR}")

# Sha256 the adapter binary so the manifest can record it (Leo's pin discipline)
adapter_safetensors = next(ADAPTER_DIR.glob("adapter_model.safetensors"), None) \\
                    or next(ADAPTER_DIR.glob("adapter_model.bin"), None)
adapter_sha = (
    hashlib.sha256(adapter_safetensors.read_bytes()).hexdigest()
    if adapter_safetensors else None
)

# Lineage from the seed_00 manifest
seed_manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))

manifest = {
    "run_id"               : RUN_ID,
    "base_model"           : BASE_MODEL,
    "tokenizer_revision"   : getattr(tokenizer, "revision", None) or "unset",
    "adapter_sha256"       : adapter_sha,
    "training_split"       : {
        "seed_index"   : seed_manifest["seed_index"],
        "seed_int"     : seed_manifest["seed_int"],
        "seedhash_input": seed_manifest["seedhash_input"],
        "source_jsonl_sha256": seed_manifest["source_jsonl_sha256"],
        "train_file_sha256": seed_manifest["file_sha256"]["train"],
        "valid_file_sha256": seed_manifest["file_sha256"]["valid"],
        "test_file_sha256" : seed_manifest["file_sha256"]["test"],
    },
    "recipe": {
        "method"             : "bf16-LoRA",
        "r"                  : LORA_R,
        "alpha"              : LORA_ALPHA,
        "target_modules"     : LORA_TARGETS,
        "lora_dropout"       : LORA_DROPOUT,
        "max_seq_length"     : MAX_SEQ_LENGTH,
        "epochs"             : NUM_EPOCHS,
        "learning_rate"      : LEARNING_RATE,
        "lr_scheduler"       : LR_SCHEDULER,
        "warmup_ratio"       : WARMUP_RATIO,
        "weight_decay"       : WEIGHT_DECAY,
        "optim"              : OPTIM,
        "per_device_batch"   : PER_DEVICE_BATCH_SIZE,
        "grad_accum_steps"   : GRAD_ACCUM_STEPS,
        "effective_batch"    : PER_DEVICE_BATCH_SIZE * GRAD_ACCUM_STEPS,
        "loss_masking"       : "train_on_responses_only",
        "random_seed"        : RANDOM_SEED,
    },
    "metrics": {
        "final_train_loss" : trainer_stats.metrics.get("train_loss"),
        "best_eval_loss"   : trainer_stats.metrics.get("eval_loss"),
        "runtime_seconds"  : runtime,
        "runtime_minutes"  : round(runtime/60, 2),
        "peak_vram_gb"     : end_mem,
        "peak_vram_pct"    : round(end_mem / (gpu.total_memory/1024**3) * 100, 1),
    },
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
(RUN_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"manifest saved  : {RUN_DIR / 'manifest.json'}")"""))

# ============================================================================
# Evaluation on test
# ============================================================================
C(md("""## 12. Evaluate on the held-out test split

The test split was untouched during training. We:
1. Switch the model to inference mode (Unsloth fast path).
2. Run greedy-ish generation (T=0.7, top_p=0.8, top_k=20 — Qwen3-Instruct defaults).
3. For each test record, parse the predicted answer per question type and compare
   to `meta.id`'s gold answer recovered from the source.
4. Compute accuracy by question type and by primary Bloom level.
5. Save per-record predictions to `models/runs/<run_id>/test_predictions.jsonl`
   and the aggregate metrics to `test_metrics.json`."""))

C(code("""FastLanguageModel.for_inference(model)
print("model switched to inference mode.")"""))

C(code("""import json, re
from tqdm.auto import tqdm

def extract_predicted(qtype: str, generation: str) -> str | None:
    \"\"\"Best-effort extraction of the model's predicted answer.\"\"\"
    g = (generation or "").strip()
    if not g:
        return None
    if qtype == "Multiple Choice":
        # First **A**/**B**/**C**/**D** wins; fall back to first standalone A-D
        m = re.search(r"\\*\\*([A-E])\\*\\*", g)
        if m: return m.group(1)
        m = re.search(r"\\b([A-E])\\b", g)
        return m.group(1) if m else None
    if qtype == "True/False":
        if re.search(r"\\b(TRUE|True|true)\\b", g): return "TRUE"
        if re.search(r"\\b(FALSE|False|false)\\b", g): return "FALSE"
        return None
    if qtype == "Matching":
        m = re.search(r"\\b(\\d{1,2})\\b", g)
        return m.group(1) if m else None
    # Essay/Problem — no automatic scoring; log only
    return g  # the full generation, for qualitative review

def gold_for(rec: dict) -> str:
    \"\"\"Pull the gold answer from the assistant message.
    The training-side renderer emits MC as '**X**', TF as '**TRUE**/**FALSE**',
    Matching as the plain number. Strip markdown and surrounding text.\"\"\"
    asst = rec["messages"][2]["content"].strip()
    qtype = rec["meta"]["type"]
    if qtype == "Multiple Choice":
        m = re.match(r"^\\*\\*([A-E])\\*\\*", asst)
        return m.group(1) if m else asst[:1]
    if qtype == "True/False":
        m = re.match(r"^\\*\\*(TRUE|FALSE)\\*\\*", asst, re.IGNORECASE)
        return m.group(1).upper() if m else asst.upper().split()[0]
    if qtype == "Matching":
        m = re.match(r"^(\\d{1,2})", asst)
        return m.group(1) if m else asst[:2]
    return asst  # Essay/Problem

predictions = []
for rec in tqdm(dataset["test"], desc="generating"):
    # Rebuild [system, user] for inference (drop the assistant)
    messages = [{"role": m["role"], "content": m["content"]} for m in rec["messages"][:2]]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt").to("cuda")
    qtype = rec["meta"]["type"]
    max_new = 32 if qtype in ("Multiple Choice", "True/False", "Matching") else 512
    out = model.generate(
        **inputs,
        max_new_tokens = max_new,
        do_sample      = True,
        temperature    = 0.7, top_p = 0.8, top_k = 20,
        pad_token_id   = tokenizer.pad_token_id or tokenizer.eos_token_id,
    )
    generation = tokenizer.decode(
        out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
    )
    predictions.append({
        "id"           : rec["meta"]["id"],
        "type"         : qtype,
        "primary_bloom": rec["meta"]["primary_bloom"],
        "chapter"      : rec["meta"]["chapter"],
        "gold"         : gold_for(rec),
        "pred"         : extract_predicted(qtype, generation),
        "generation"   : generation,
    })

pred_path = RUN_DIR / "test_predictions.jsonl"
with pred_path.open("w", encoding="utf-8") as fh:
    for p in predictions:
        fh.write(json.dumps(p, ensure_ascii=False) + "\\n")
print(f"wrote {pred_path}  ({len(predictions)} predictions)")"""))

C(code("""from collections import Counter, defaultdict

# Aggregate accuracy by question type and by Bloom
by_type     = defaultdict(lambda: Counter())
by_bloom    = defaultdict(lambda: Counter())
by_chapter  = defaultdict(lambda: Counter())
overall     = Counter()

SCORABLE = {"Multiple Choice", "True/False", "Matching"}

for p in predictions:
    qtype = p["type"]
    if qtype not in SCORABLE:
        # Essay/Problem — count separately but don't accuracy-score
        by_type[qtype]["skipped_essay"] += 1
        continue
    gold = (p["gold"] or "").strip().upper()
    pred = (p["pred"] or "").strip().upper()
    correct = (gold == pred) and bool(gold)
    by_type[qtype]["correct" if correct else "wrong"] += 1
    by_bloom[p["primary_bloom"]]["correct" if correct else "wrong"] += 1
    by_chapter[p["chapter"]]["correct" if correct else "wrong"] += 1
    overall["correct" if correct else "wrong"] += 1

def pct(c):
    n = c["correct"] + c["wrong"]
    return f"{100*c['correct']/n:.1f}%  ({c['correct']}/{n})" if n else "  —  "

print("=== Accuracy by question type (scorable types only) ===")
for t, c in by_type.items():
    if t in SCORABLE:
        print(f"  {t:<20s}: {pct(c)}")
    else:
        print(f"  {t:<20s}: skipped (essay — see test_predictions.jsonl)")
print()
print("=== Accuracy by primary Bloom ===")
for b, c in sorted(by_bloom.items()):
    print(f"  {b:<12s}: {pct(c)}")
print()
print("=== Accuracy by chapter ===")
for ch, c in sorted(by_chapter.items()):
    print(f"  Ch {ch:>2}: {pct(c)}")
print()
print(f"=== Overall (scorable, n={overall['correct']+overall['wrong']}): {pct(overall)} ===")

metrics = {
    "overall_accuracy"   : (overall["correct"] / (overall["correct"]+overall["wrong"])
                            if (overall["correct"]+overall["wrong"]) else None),
    "by_question_type"   : {t: dict(c) for t, c in by_type.items()},
    "by_primary_bloom"   : {b: dict(c) for b, c in by_bloom.items()},
    "by_chapter"         : {ch: dict(c) for ch, c in by_chapter.items()},
    "n_predictions"      : len(predictions),
    "n_scorable"         : overall["correct"] + overall["wrong"],
}
(RUN_DIR / "test_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(f"wrote {RUN_DIR / 'test_metrics.json'}")"""))

# ============================================================================
# Optional: GGUF export for llama.cpp / Ollama (Windows-friendly serving)
# ============================================================================
C(md("""## 13. (Optional) Export to GGUF for llama.cpp / Ollama serving

vLLM does not work on Windows (no native `vllm._C`). For Windows-native production
serving, export the merged model to GGUF and load it with **llama.cpp** or **Ollama**.

Flip the `if False:` guard to `if True:` to run. Pick one quantization:

- `q4_k_m` — recommended for a 4B model on a 4090 Laptop. ~2.5 GB file, near-full accuracy.
- `q8_0` — larger (~4.3 GB) but lower quantization loss; use if you have spare disk.
- `f16` — full bf16 export (~7.5 GB), no quantization loss.

This pulls and builds `llama.cpp` on first run (~5 min) and emits a `.gguf` file
under `models/runs/<run_id>/`."""))

C(code("""if False:  # flip to True to export
    GGUF_QUANT = "q4_k_m"   # or "q8_0", "q5_k_m", "f16"
    model.save_pretrained_gguf(
        str(RUN_DIR / f"gguf_{GGUF_QUANT}"),
        tokenizer,
        quantization_method = GGUF_QUANT,
    )
    print(f"GGUF written to {RUN_DIR / f'gguf_{GGUF_QUANT}'}")"""))

# ============================================================================
# Footer
# ============================================================================
C(md("""## What's next

Artifacts produced under `models/runs/qwen3_4b_seed00_bf16_lora/`:

- `adapter/` — the LoRA safetensors + tokenizer + config. Re-load with `FastLanguageModel.from_pretrained` for Unsloth-native inference.
- `manifest.json` — recipe + lineage + metrics (Leo's pin discipline).
- `test_predictions.jsonl` — per-record predictions for qualitative review (especially Essay/Problem rationales).
- `test_metrics.json` — aggregate accuracy by question type / Bloom / chapter.
- `gguf_<quant>/` — (optional, if §13 was run) GGUF export for llama.cpp / Ollama.

### Serving paths on Windows

| Option | Stack | Notes |
|---|---|---|
| Quickest local inference | `FastLanguageModel.from_pretrained(adapter_dir) + FastLanguageModel.for_inference(model)` | Same env as training |
| Production-grade local | llama.cpp or Ollama on the GGUF export from §13 | Runs natively on Windows |
| Production-grade if Linux available | vLLM via WSL2 or Docker, mounted at the adapter dir | Highest throughput but requires WSL/Docker setup |

### To launch additional seeds for the variance estimate

Copy this notebook and change `SEED_DIR` + `RUN_ID` in cell §2 to one of:

- `seed_01__1884065545`
- `seed_02__1805455021`
- `seed_03__880639735`
- `seed_04__1797866777`

Aggregate `test_metrics.json` across the 5 runs for `mean ± std` of test accuracy."""))


nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "Python (unsloth)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12.9",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(CELLS)} cells)")
