#!/usr/bin/env python3
"""
eval/diff_runs.py  — Vera's delta reporter between two eval runs.

Usage
-----
python eval/diff_runs.py <baseline_dir> <candidate_dir> \\
    [--baseline-label LABEL] [--candidate-label LABEL] \\
    [--write-md]

Reads test_metrics.json from each directory.
Computes pp deltas per slice cell.
Writes Markdown to stdout.
Optionally writes <candidate_dir>/diff_vs_<baseline_label>.md.

Exit codes
----------
0 — no regressions (no cell delta < -1.0 pp)
1 — at least one cell delta < -1.0 pp
"""

import argparse
import json
import sys
from pathlib import Path


def load_metrics(d: Path) -> dict:
    mp = d / "test_metrics.json"
    if not mp.exists():
        print(f"[diff_runs] ERROR: {mp} does not exist.", file=sys.stderr)
        sys.exit(1)
    with open(mp) as f:
        return json.load(f)


def pct(x) -> str:
    if x is None:
        return "N/A"
    return f"{x*100:.1f}%"


def delta_str(base_acc, cand_acc) -> str:
    if base_acc is None or cand_acc is None:
        return "N/A"
    d = (cand_acc - base_acc) * 100
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f} pp"


def regression(base_acc, cand_acc, threshold: float = -1.0) -> bool:
    if base_acc is None or cand_acc is None:
        return False
    return (cand_acc - base_acc) * 100 < threshold


def build_report(
    bm: dict,
    cm: dict,
    baseline_label: str,
    candidate_label: str,
    regression_threshold: float = -1.0,
) -> tuple[str, bool]:
    """Return (markdown_text, has_regression)."""
    lines: list[str] = []
    has_regression = False

    lines.append(f"# Eval delta: `{candidate_label}` vs baseline `{baseline_label}`\n")
    lines.append(f"- Baseline run_id  : `{bm.get('run_id', '?')}`")
    lines.append(f"- Candidate run_id : `{cm.get('run_id', '?')}`")
    lines.append(f"- Generated at     : `{cm.get('generated_at', '?')}`")
    lines.append(f"- N questions (candidate): {cm.get('n_questions', '?')}")
    lines.append(f"- Adapter SHA256   : `{cm.get('adapter_sha256', '?')[:16]}...`")
    lines.append(f"- Test split SHA256: `{cm.get('test_split_sha256', '?')[:16]}...`")
    lines.append("")

    # Overall
    b_ov = bm.get("overall_accuracy_scorable")
    c_ov = cm.get("overall_accuracy_scorable")
    flag = " <<< REGRESSION" if regression(b_ov, c_ov, regression_threshold) else ""
    if regression(b_ov, c_ov, regression_threshold):
        has_regression = True
    lines.append("## Overall")
    lines.append(f"| | Baseline | Candidate | Delta |")
    lines.append(f"|---|---|---|---|")
    lines.append(f"| Scorable accuracy | {pct(b_ov)} | {pct(c_ov)} | {delta_str(b_ov, c_ov)}{flag} |")
    lines.append(f"| N scorable | {bm.get('n_scorable','?')} | {cm.get('n_scorable','?')} | — |")
    lines.append(f"| N judge_pending | {bm.get('n_judge_pending','?')} | {cm.get('n_judge_pending','?')} | — |")
    lines.append("")

    # by_primary_bloom
    lines.append("## By Bloom level")
    lines.append("| Bloom | Baseline | Candidate | Delta |")
    lines.append("|---|---|---|---|")
    blooms = sorted(
        set(list(bm.get("by_primary_bloom", {}).keys()) + list(cm.get("by_primary_bloom", {}).keys()))
    )
    for b in blooms:
        b_acc = (bm.get("by_primary_bloom", {}).get(b) or {}).get("accuracy")
        c_acc = (cm.get("by_primary_bloom", {}).get(b) or {}).get("accuracy")
        flag = " <<< REGRESSION" if regression(b_acc, c_acc, regression_threshold) else ""
        if regression(b_acc, c_acc, regression_threshold):
            has_regression = True
        lines.append(f"| {b} | {pct(b_acc)} | {pct(c_acc)} | {delta_str(b_acc, c_acc)}{flag} |")
    lines.append("")

    # by_chapter
    lines.append("## By Chapter")
    lines.append("| Chapter | Baseline | Candidate | Delta |")
    lines.append("|---|---|---|---|")
    chapters = sorted(
        set(list(bm.get("by_chapter", {}).keys()) + list(cm.get("by_chapter", {}).keys())),
        key=lambda x: int(x) if x.isdigit() else 999,
    )
    for ch in chapters:
        b_acc = (bm.get("by_chapter", {}).get(ch) or {}).get("accuracy")
        c_acc = (cm.get("by_chapter", {}).get(ch) or {}).get("accuracy")
        flag = " <<< REGRESSION" if regression(b_acc, c_acc, regression_threshold) else ""
        if regression(b_acc, c_acc, regression_threshold):
            has_regression = True
        lines.append(f"| Ch {ch} | {pct(b_acc)} | {pct(c_acc)} | {delta_str(b_acc, c_acc)}{flag} |")
    lines.append("")

    # by_question_type
    lines.append("## By Question Type")
    lines.append("| Type | Baseline | Candidate | Delta |")
    lines.append("|---|---|---|---|")
    qtypes = sorted(
        set(list(bm.get("by_question_type", {}).keys()) + list(cm.get("by_question_type", {}).keys()))
    )
    for qt in qtypes:
        b_acc = (bm.get("by_question_type", {}).get(qt) or {}).get("accuracy")
        c_acc = (cm.get("by_question_type", {}).get(qt) or {}).get("accuracy")
        flag = " <<< REGRESSION" if regression(b_acc, c_acc, regression_threshold) else ""
        if regression(b_acc, c_acc, regression_threshold):
            has_regression = True
        lines.append(f"| {qt} | {pct(b_acc)} | {pct(c_acc)} | {delta_str(b_acc, c_acc)}{flag} |")
    lines.append("")

    # by_difficulty (canonical values look like "1 Easy" / "2 Medium" / "3 Hard"
    # so lexical sort matches the natural ordering)
    lines.append("## By Difficulty")
    lines.append("| Difficulty | Baseline | Candidate | Delta |")
    lines.append("|---|---|---|---|")
    diffs = sorted(
        set(list(bm.get("by_difficulty", {}).keys()) + list(cm.get("by_difficulty", {}).keys()))
    )
    for d in diffs:
        b_acc = (bm.get("by_difficulty", {}).get(d) or {}).get("accuracy")
        c_acc = (cm.get("by_difficulty", {}).get(d) or {}).get("accuracy")
        flag = " <<< REGRESSION" if regression(b_acc, c_acc, regression_threshold) else ""
        if regression(b_acc, c_acc, regression_threshold):
            has_regression = True
        lines.append(f"| {d} | {pct(b_acc)} | {pct(c_acc)} | {delta_str(b_acc, c_acc)}{flag} |")
    lines.append("")

    # Mechanical checks
    lines.append("## Mechanical Checks")
    bmc = bm.get("mechanical_checks", {})
    cmc = cm.get("mechanical_checks", {})

    check_keys = [
        ("je_balance_violations",       "JE balance violations"),
        ("missing_citation_violations",  "Missing citation (Remember/Understand)"),
        ("arith_in_prose_violations",    "Arithmetic in prose at Apply+"),
        ("reasoning_pattern_drift",      "Reasoning-pattern drift"),
        ("smell_introduced_by_model",    "Standards-smell introduced by model"),
    ]
    lines.append("| Check | Baseline | Candidate |")
    lines.append("|---|---|---|")
    for key, label in check_keys:
        bv = bmc.get(key, "N/A")
        cv = cmc.get(key, "N/A")
        lines.append(f"| {label} | {bv} | {cv} |")

    lines.append("")
    lines.append(f"**Gate (candidate):** {'PASS' if cmc.get('gate_pass') else 'FAIL'}")
    lines.append(f"**Smell gate (candidate):** {'PASS' if cmc.get('smell_gate_pass') else 'ADVISORY'}")
    lines.append("")

    if has_regression:
        lines.append("> **REGRESSION DETECTED** — one or more cells fell > 1.0 pp vs baseline.")
    else:
        lines.append("> No regressions detected (all cell deltas >= -1.0 pp).")

    return "\n".join(lines), has_regression


def main() -> None:
    ap = argparse.ArgumentParser(description="Diff two eval runs.")
    ap.add_argument("baseline_dir",  help="Directory with baseline test_metrics.json")
    ap.add_argument("candidate_dir", help="Directory with candidate test_metrics.json")
    ap.add_argument("--baseline-label",  default=None, help="Override baseline label")
    ap.add_argument("--candidate-label", default=None, help="Override candidate label")
    ap.add_argument("--write-md", action="store_true",
                    help="Write diff_vs_<baseline>.md into candidate_dir")
    args = ap.parse_args()

    baseline_dir  = Path(args.baseline_dir).resolve()
    candidate_dir = Path(args.candidate_dir).resolve()
    baseline_label  = args.baseline_label  or baseline_dir.name
    candidate_label = args.candidate_label or candidate_dir.name

    bm = load_metrics(baseline_dir)
    cm = load_metrics(candidate_dir)

    report, has_regression = build_report(bm, cm, baseline_label, candidate_label)
    print(report)

    if args.write_md:
        out_path = candidate_dir / f"diff_vs_{baseline_label}.md"
        with open(out_path, "w") as f:
            f.write(report)
        print(f"\n[diff_runs] wrote {out_path}", file=sys.stderr)

    sys.exit(1 if has_regression else 0)


if __name__ == "__main__":
    main()
