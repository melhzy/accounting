#!/usr/bin/env python3
"""
eval/run.py  — Vera's regression harness for the accounting LLM adapter.

Runs the fine-tuned adapter (or base model) over a test split and emits:
  <run-dir>/test_predictions.jsonl   — one row per question
  <run-dir>/test_metrics.json        — accuracy + mechanical checks

Usage
-----
python eval/run.py \\
    --run-id qwen3-4b-4bit-qlora-s00-r0 \\
    --split  eval/sft/splits/seed_00__351199285/test.jsonl \\
    --adapter models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0 \\
    [--max-new-tokens-short 32] [--max-new-tokens-long 512] \\
    [--temperature 0.0] [--top-p 1.0] \\
    [--limit N]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── repo root detection ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT   = SCRIPT_DIR.parent
CANONICAL_JSONL = REPO_ROOT / "eval" / "spiceland9e.jsonl"

# ── import mechanical checks + seeding (same flat-module package) ───────────
sys.path.insert(0, str(SCRIPT_DIR))
from mechanical_checks import run_checks  # noqa: E402
from seeding import seed_everything  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# SHA-256 helpers
# ════════════════════════════════════════════════════════════════════════════

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file_prefix(path: Path, n: int = 16) -> str:
    return sha256_file(path)[:n]


# ════════════════════════════════════════════════════════════════════════════
# Canonical JSONL loader
# ════════════════════════════════════════════════════════════════════════════

def load_canonical(path: Path) -> dict[str, Any]:
    """Return {id: record} from the canonical eval/spiceland9e.jsonl."""
    data: dict[str, Any] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            data[r["id"]] = r
    return data


# ════════════════════════════════════════════════════════════════════════════
# Answer extraction helpers
# ════════════════════════════════════════════════════════════════════════════

_MC_PATTERN   = re.compile(r"\*{0,2}\b([A-Za-z])\b\*{0,2}")
_TF_TRUE_PAT  = re.compile(r"\bTRUE\b", re.IGNORECASE)
_TF_FALSE_PAT = re.compile(r"\bFALSE\b", re.IGNORECASE)
_BOLD_CLEAN   = re.compile(r"\*+")


def extract_mc_answer(generation: str) -> str | None:
    """Extract first bold or bare single letter from MC generation."""
    # Prefer **X** pattern first
    bold = re.findall(r"\*\*([A-Za-z])\*\*", generation)
    if bold:
        return bold[0].upper()
    # Fall back to first isolated letter
    m = _MC_PATTERN.search(generation)
    if m:
        return m.group(1).upper()
    return None


def extract_tf_answer(generation: str) -> str | None:
    """Extract TRUE or FALSE from TF generation."""
    # Prefer **TRUE** / **FALSE**
    bold_true  = re.search(r"\*\*(TRUE)\*\*",  generation, re.IGNORECASE)
    bold_false = re.search(r"\*\*(FALSE)\*\*", generation, re.IGNORECASE)
    if bold_true and bold_false:
        # take whichever comes first
        return "TRUE" if bold_true.start() < bold_false.start() else "FALSE"
    if bold_true:
        return "TRUE"
    if bold_false:
        return "FALSE"
    if _TF_TRUE_PAT.search(generation):
        return "TRUE"
    if _TF_FALSE_PAT.search(generation):
        return "FALSE"
    return None


def extract_matching_answer(generation: str) -> str | None:
    """
    Matching in Spiceland test bank is always a single letter answer
    (one option matched to one descriptor).  Same extraction as MC.
    """
    return extract_mc_answer(generation)


# ════════════════════════════════════════════════════════════════════════════
# Scoring
# ════════════════════════════════════════════════════════════════════════════

def score_prediction(
    qtype: str,
    gold: str,
    pred: str | None,
    generation: str,
) -> tuple[bool | None, bool]:
    """
    Returns (correct: bool|None, scorable: bool).
    correct=None means judge_pending (Essay/Problem in r0).
    """
    if qtype == "Essay/Problem":
        return None, False  # judge_pending

    if pred is None:
        return False, True  # extraction failed → wrong

    if qtype == "Multiple Choice":
        return pred.upper() == gold.strip().upper(), True

    if qtype == "True/False":
        return pred.upper() == gold.strip().upper(), True

    if qtype == "Matching":
        # Single-letter exact match (set-equality trivially holds for single pairs)
        return pred.upper() == gold.strip().upper(), True

    # Unknown type — skip
    return None, False


# ════════════════════════════════════════════════════════════════════════════
# Model loader
# ════════════════════════════════════════════════════════════════════════════

def load_model_and_tokenizer(adapter_dir: Path, temperature: float, top_p: float):
    """Load 4-bit QLoRA adapter via PEFT + unsloth tokenizer."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    adapter_cfg_path = adapter_dir / "adapter_config.json"
    with open(adapter_cfg_path) as f:
        adapter_cfg = json.load(f)
    base_model_name = adapter_cfg["base_model_name_or_path"]
    print(f"[run.py] base model : {base_model_name}", flush=True)
    print(f"[run.py] adapter    : {adapter_dir}", flush=True)

    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_dir),
        trust_remote_code=True,
    )

    base = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=bnb_cfg,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model.eval()
    print(f"[run.py] model loaded, device_map=auto", flush=True)
    return model, tokenizer


# ════════════════════════════════════════════════════════════════════════════
# Single-question generation
# ════════════════════════════════════════════════════════════════════════════

def generate_one(
    model,
    tokenizer,
    messages: list[dict],
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> tuple[str, int, int, float]:
    """
    Returns (generation_text, n_input_tokens, n_output_tokens, latency_ms).
    """
    import torch

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    n_input = inputs["input_ids"].shape[-1]

    gen_kwargs: dict[str, Any] = dict(
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    if temperature == 0.0:
        gen_kwargs["do_sample"] = False
    else:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = temperature
        gen_kwargs["top_p"] = top_p

    t0 = time.perf_counter()
    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    # Decode only the new tokens (not the prompt)
    new_ids = output_ids[0, n_input:]
    generation = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
    n_output = new_ids.shape[0]

    return generation, n_input, n_output, latency_ms


# ════════════════════════════════════════════════════════════════════════════
# Split SHA-256 guard
# ════════════════════════════════════════════════════════════════════════════

MANIFEST_HOLDOUT_SHA = "86e2914fb83d221c86ef3db745a31164d756b7d0525ec76051cf6ef92b0857e7"


def verify_split_sha(split_path: Path) -> str:
    """
    Compute sha256 of the test split and compare against the pinned manifest value.
    STOP if mismatch — the split was tampered.
    """
    actual = sha256_file(split_path)
    if actual != MANIFEST_HOLDOUT_SHA:
        print(
            f"[FATAL] Test split SHA mismatch!\n"
            f"  expected : {MANIFEST_HOLDOUT_SHA}\n"
            f"  actual   : {actual}\n"
            f"  path     : {split_path}\n"
            "Split may have been tampered. STOPPING.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"[run.py] split sha256 OK: {actual[:16]}...", flush=True)
    return actual


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description="Run eval harness on a test split.")
    ap.add_argument("--run-id",   required=True, help="e.g. qwen3-4b-4bit-qlora-s00-r0")
    ap.add_argument("--split",    required=True, help="path to test.jsonl")
    ap.add_argument("--adapter",  required=True, help="path to adapter directory")
    ap.add_argument("--max-new-tokens-short", type=int, default=32,
                    help="token budget for MC/TF/Matching")
    ap.add_argument("--max-new-tokens-long",  type=int, default=512,
                    help="token budget for Essay/Problem")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--top-p",       type=float, default=1.0)
    ap.add_argument("--limit",    type=int, default=None,
                    help="only process first N questions (smoke test)")
    ap.add_argument("--canonical", default=None,
                    help="override path to canonical JSONL (default: eval/spiceland9e.jsonl)")
    ap.add_argument("--solver-emits-citations", action="store_true",
                    help="solver layer emits citations -> activates mechanical check #2 "
                         "(citation at Bloom Remember/Understand). Default off; r0-class "
                         "runs without a citation-emitting solver should leave this off.")
    ap.add_argument("--solver-emits-tool-calls", action="store_true",
                    help="solver layer emits tool_calls -> activates mechanical check #3 "
                         "(arithmetic-in-prose at Apply+). Default off; r0-class runs "
                         "without a tool layer should leave this off.")
    ap.add_argument("--seed", type=int, default=None,
                    help="Override the eval seed. Default: read `seed_int` from the "
                         "split's sibling manifest.json (per project seedhash policy).")
    ap.add_argument("--strict-determinism", action="store_true",
                    help="Enable cuDNN deterministic + use_deterministic_algorithms + "
                         "CUBLAS_WORKSPACE_CONFIG (slower; for ablation reproducibility).")
    args = ap.parse_args()

    split_path   = Path(args.split).resolve()
    adapter_path = Path(args.adapter).resolve()
    out_dir      = adapter_path  # write outputs alongside the adapter

    canonical_path = Path(args.canonical).resolve() if args.canonical else CANONICAL_JSONL

    # ── 0. Deterministic seeding (project policy: seedhash is the sole seed
    # derivation mechanism — see eval/seeding.py + the seeding-policy memory).
    # Default seed: the `seed_int` baked into the split's sibling manifest, so
    # the eval run inherits the exact same `seedhash`-derived seed that produced
    # the split. Must run before any torch CUDA op (i.e. before model load).
    split_manifest_path = split_path.parent / "manifest.json"
    if args.seed is not None:
        eval_seed = args.seed
    elif split_manifest_path.exists():
        eval_seed = json.loads(split_manifest_path.read_text(encoding="utf-8"))["seed_int"]
    else:
        raise RuntimeError(
            f"--seed not given and no manifest.json beside {split_path}; "
            "cannot honor the project seedhash policy."
        )
    seeding_report = seed_everything(seed_int=eval_seed, strict=args.strict_determinism)
    print(
        f"[run.py] seeding: seed_int={seeding_report.seed_int} "
        f"per_rank_seed={seeding_report.per_rank_seed_int} "
        f"topology={seeding_report.topology} strict={seeding_report.strict}",
        flush=True,
    )

    # ── 1. Verify split SHA ──────────────────────────────────────────────────
    test_split_sha = verify_split_sha(split_path)

    # ── 2. Load canonical lookup ─────────────────────────────────────────────
    print(f"[run.py] loading canonical JSONL ...", flush=True)
    canonical = load_canonical(canonical_path)
    print(f"[run.py] canonical records: {len(canonical)}", flush=True)

    # ── 3. Read test split ───────────────────────────────────────────────────
    with open(split_path) as f:
        test_rows = [json.loads(l) for l in f if l.strip()]

    if args.limit:
        test_rows = test_rows[: args.limit]
        print(f"[run.py] --limit {args.limit}: processing {len(test_rows)} rows", flush=True)
    else:
        print(f"[run.py] processing {len(test_rows)} rows", flush=True)

    # ── 4. Load model ────────────────────────────────────────────────────────
    model, tokenizer = load_model_and_tokenizer(adapter_path, args.temperature, args.top_p)

    # Adapter SHA
    adapter_safetensors = adapter_path / "adapter_model.safetensors"
    adapter_sha = sha256_file_prefix(adapter_safetensors, n=64) if adapter_safetensors.exists() else "unknown"

    # ── 5. Inference loop ────────────────────────────────────────────────────
    predictions: list[dict[str, Any]] = []
    n_correct = 0
    n_scorable = 0
    n_judge_pending = 0

    for i, row in enumerate(test_rows):
        meta    = row["meta"]
        qid     = meta["id"]
        qtype   = meta["type"]
        chapter = meta["chapter"]
        bloom   = meta.get("primary_bloom", "Unknown")

        # Gold answer + difficulty from canonical record
        can_rec    = canonical.get(qid, {})
        gold       = can_rec.get("gold_answer", "")
        difficulty = can_rec.get("difficulty") or "Unknown"

        # Build messages: use the prompt from the split (includes system + user)
        # strip the last assistant turn (that's what we predict)
        messages = [m for m in row["messages"] if m["role"] != "assistant"]

        # Token budget
        is_long = qtype in ("Essay/Problem",)
        max_new_tokens = args.max_new_tokens_long if is_long else args.max_new_tokens_short

        # Generate
        try:
            generation, n_in, n_out, latency_ms = generate_one(
                model, tokenizer, messages,
                max_new_tokens=max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
            )
        except Exception as exc:
            print(f"[run.py] ERROR on {qid}: {exc}", file=sys.stderr)
            generation, n_in, n_out, latency_ms = "", 0, 0, 0.0

        # Extract predicted answer
        if qtype == "Multiple Choice":
            pred = extract_mc_answer(generation)
        elif qtype == "True/False":
            pred = extract_tf_answer(generation)
        elif qtype == "Matching":
            pred = extract_matching_answer(generation)
        else:
            pred = None  # Essay/Problem — no extraction

        # Score
        correct, scorable = score_prediction(qtype, gold, pred, generation)

        if correct is None:  # Essay/Problem
            n_judge_pending += 1
        elif scorable:
            n_scorable += 1
            if correct:
                n_correct += 1

        out_row: dict[str, Any] = {
            "question_id":    qid,
            "type":           qtype,
            "primary_bloom":  bloom,
            "chapter":        chapter,
            "difficulty":     difficulty,
            "gold":           gold,
            "pred":           pred,
            "correct":        correct,
            "scorable":       scorable,
            "judge_pending":  (correct is None),
            "generation":     generation,
            "n_input_tokens": n_in,
            "n_output_tokens":n_out,
            "latency_ms":     round(latency_ms, 1),
            # r0 stub fields (no tool use, no citations yet)
            "tool_calls":     [],
            "citations":      [],
        }
        predictions.append(out_row)

        if (i + 1) % 20 == 0 or (i + 1) == len(test_rows):
            acc = n_correct / n_scorable if n_scorable else 0.0
            print(
                f"[run.py] {i+1}/{len(test_rows)}  "
                f"scorable={n_scorable}  correct={n_correct}  "
                f"acc={acc:.3f}  judge_pending={n_judge_pending}",
                flush=True,
            )

    # ── 6. Run mechanical checks ─────────────────────────────────────────────
    print("[run.py] running mechanical checks ...", flush=True)
    mech = run_checks(
        predictions,
        canonical,
        solver_emits_citations=args.solver_emits_citations,
        solver_emits_tool_calls=args.solver_emits_tool_calls,
    )

    # ── 7. Build slice tables ─────────────────────────────────────────────────
    def slice_accuracy(preds: list[dict]) -> dict[str, Any]:
        """Compute accuracy dict for a slice."""
        c = s = jp = 0
        for p in preds:
            if p["judge_pending"]:
                jp += 1
            elif p["scorable"]:
                s += 1
                if p["correct"]:
                    c += 1
        return {
            "correct": c,
            "scorable": s,
            "judge_pending": jp,
            "accuracy": round(c / s, 4) if s else None,
        }

    # by_question_type
    by_type: dict[str, Any] = {}
    for qtype in ("Multiple Choice", "True/False", "Matching", "Essay/Problem"):
        subset = [p for p in predictions if p["type"] == qtype]
        by_type[qtype] = slice_accuracy(subset)

    # by_primary_bloom
    blooms_present = sorted({p["primary_bloom"] for p in predictions})
    by_bloom: dict[str, Any] = {}
    for b in blooms_present:
        subset = [p for p in predictions if p["primary_bloom"] == b]
        by_bloom[b] = slice_accuracy(subset)

    # by_chapter
    chapters_present = sorted({p["chapter"] for p in predictions})
    by_chapter: dict[str, Any] = {}
    for ch in chapters_present:
        subset = [p for p in predictions if p["chapter"] == ch]
        by_chapter[str(ch)] = slice_accuracy(subset)

    # by_difficulty (canonical JSONL carries values like "1 Easy" / "2 Medium" / "3 Hard")
    difficulties_present = sorted({p["difficulty"] for p in predictions})
    by_difficulty: dict[str, Any] = {}
    for d in difficulties_present:
        subset = [p for p in predictions if p["difficulty"] == d]
        by_difficulty[d] = slice_accuracy(subset)

    overall_acc = round(n_correct / n_scorable, 4) if n_scorable else None

    metrics: dict[str, Any] = {
        "run_id":              args.run_id,
        "adapter_sha256":      adapter_sha,
        "test_split_sha256":   test_split_sha,
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "n_questions":         len(predictions),
        "n_scorable":          n_scorable,
        "n_judge_pending":     n_judge_pending,
        "overall_accuracy_scorable": overall_acc,
        "by_question_type":    by_type,
        "by_primary_bloom":    by_bloom,
        "by_chapter":          by_chapter,
        "by_difficulty":       by_difficulty,
        "generation_config": {
            "max_new_tokens_short":     args.max_new_tokens_short,
            "max_new_tokens_long":      args.max_new_tokens_long,
            "temperature":              args.temperature,
            "top_p":                    args.top_p,
            "limit":                    args.limit,
            "solver_emits_citations":   args.solver_emits_citations,
            "solver_emits_tool_calls":  args.solver_emits_tool_calls,
        },
        "seeding_report":     seeding_report.to_dict(),
        "mechanical_checks":  mech,
    }

    # ── 8. Write outputs ──────────────────────────────────────────────────────
    pred_path    = out_dir / "test_predictions.jsonl"
    metrics_path = out_dir / "test_metrics.json"

    with open(pred_path, "w") as f:
        for row in predictions:
            f.write(json.dumps(row) + "\n")
    print(f"[run.py] wrote {len(predictions)} predictions → {pred_path}", flush=True)

    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[run.py] wrote metrics → {metrics_path}", flush=True)

    # ── 9. Print summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"OVERALL accuracy (scorable): {overall_acc:.4f}" if overall_acc else "OVERALL: no scorable rows")
    print(f"  scorable     : {n_scorable}")
    print(f"  judge_pending: {n_judge_pending}")
    print(f"  mech gate    : {'PASS' if mech['gate_pass'] else 'FAIL'}")
    print(f"  smell gate   : {'PASS' if mech['smell_gate_pass'] else 'ADVISORY'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
