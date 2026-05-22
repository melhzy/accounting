"""One-shot: re-score MC/TF/Matching from existing generations with the
corrected extractors, then rewrite test_metrics.json. Run inside the container
(where root can write the root-owned artifact files), or on the host once
ownership is reclaimed.

Idempotent: a second run is a no-op if extractors agree with the file state.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def find_repo() -> Path:
    workspace = Path("/workspace")
    if workspace.is_dir() and (workspace / "eval" / "sft" / "splits").is_dir():
        return workspace
    p = Path(__file__).resolve()
    for d in p.parents:
        if (d / ".git").is_dir() or (d / "eval" / "sft" / "splits").is_dir():
            return d
    raise RuntimeError("cannot find repo root")


REPO = find_repo()
PRED_PATH = REPO / "models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/eval_rerun/test_predictions.jsonl"
METRICS_PATH = REPO / "models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/eval_rerun/test_metrics.json"
TEST_JSONL = REPO / "eval/sft/splits/seed_00__351199285/test.jsonl"


def extract_predicted(qtype, g):
    g = (g or "").strip()
    if not g:
        return None
    if qtype == "Multiple Choice":
        m = re.search(r"\*\*([A-E])\*\*", g)
        if m:
            return m.group(1)
        m = re.search(r"\b([A-E])\b", g)
        return m.group(1) if m else None
    if qtype == "True/False":
        if re.search(r"\b(TRUE|True|true)\b", g):
            return "TRUE"
        if re.search(r"\b(FALSE|False|false)\b", g):
            return "FALSE"
        return None
    if qtype == "Matching":
        m = re.search(r"\b([A-Z])\b", g)
        if m:
            return m.group(1)
        m = re.search(r"\b(\d{1,2})\b", g)
        return m.group(1) if m else None
    return g


def gold_for(rec):
    asst = rec["messages"][2]["content"].strip()
    qtype = rec["meta"]["type"]
    if qtype == "Multiple Choice":
        m = re.match(r"^\*\*([A-E])\*\*", asst)
        return m.group(1) if m else asst[:1]
    if qtype == "True/False":
        m = re.match(r"^\*\*(TRUE|FALSE)\*\*", asst, re.IGNORECASE)
        return m.group(1).upper() if m else asst.upper().split()[0]
    if qtype == "Matching":
        m = re.match(r"^([A-Z])\b", asst)
        return m.group(1) if m else asst[:1]
    return asst


SCORABLE = {"Multiple Choice", "True/False", "Matching"}


def main() -> int:
    test_by_id = {}
    with TEST_JSONL.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            test_by_id[r["meta"]["id"]] = r

    preds = [json.loads(l) for l in PRED_PATH.open(encoding="utf-8")]
    print(f"loaded {len(preds)} predictions from {PRED_PATH}", flush=True)

    changes = defaultdict(int)
    for p in preds:
        if p["type"] not in SCORABLE:
            continue
        rec = test_by_id[p["question_id"]]
        new_gold = gold_for(rec)
        new_pred = extract_predicted(p["type"], p["generation"])
        new_correct = bool(new_gold and new_pred and new_gold.strip().upper() == new_pred.strip().upper())
        if p.get("correct") != new_correct or p.get("pred") != new_pred:
            changes[p["type"]] += 1
        p["gold"] = new_gold
        p["pred"] = new_pred
        p["correct"] = new_correct
        p["scorable"] = True
        p["judge_pending"] = False

    print(f"re-scored changes: {dict(changes)}", flush=True)

    with PRED_PATH.open("w", encoding="utf-8") as fh:
        for p in preds:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {PRED_PATH}", flush=True)

    def ab():
        return {"correct": 0, "scorable": 0, "judge_pending": 0}

    by_type, by_bloom, by_chapter, overall = defaultdict(ab), defaultdict(ab), defaultdict(ab), ab()
    for p in preds:
        for b in (by_type[p["type"]], by_bloom[p["primary_bloom"]], by_chapter[p["chapter"]], overall):
            if p["judge_pending"]:
                b["judge_pending"] += 1
            else:
                b["scorable"] += 1
                if p["correct"]:
                    b["correct"] += 1

    def wacc(b):
        return {**b, "accuracy": (b["correct"] / b["scorable"]) if b["scorable"] else None}

    prev = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    metrics = {
        **prev,
        "n_questions": len(preds),
        "n_scorable": overall["scorable"],
        "n_judge_pending": overall["judge_pending"],
        "overall_accuracy_scorable": round(overall["correct"] / overall["scorable"], 4) if overall["scorable"] else None,
        "by_question_type": {k: wacc(v) for k, v in by_type.items()},
        "by_primary_bloom": {k: wacc(v) for k, v in sorted(by_bloom.items())},
        "by_chapter": {str(k): wacc(v) for k, v in sorted(by_chapter.items())},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"wrote {METRICS_PATH}", flush=True)

    print(f"\n=== overall: {metrics['overall_accuracy_scorable']:.2%}  ({overall['correct']}/{overall['scorable']}) ===", flush=True)
    for t, v in metrics["by_question_type"].items():
        acc = f"{v['accuracy']:.2%}" if v["accuracy"] is not None else "  —  "
        print(f"  {t:<18s}: {acc}  ({v['correct']}/{v['scorable']})", flush=True)
    print("\nby primary bloom:", flush=True)
    for b, v in metrics["by_primary_bloom"].items():
        acc = f"{v['accuracy']:.2%}" if v["accuracy"] is not None else "  —  "
        print(f"  {b:<12s}: {acc}  ({v['correct']}/{v['scorable']})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
