"""Cross-validate every Excel-Word chapter pair in the Spiceland 9e test bank.

Goal: surface conversion-quality defects before LLM training.

Writes:
  eval/_audit/audit_report.json   machine-readable
  eval/_audit/audit_report.md     human-readable summary

Run from repo root:
  python eval/_audit/audit_all.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from docx import Document

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "Intermediate Financial Accounting test bank"
EXCEL_DIR = SRC / "excel"
WORD_DIR = SRC / "word"
OUT_DIR = REPO_ROOT / "eval" / "_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_COLUMNS = [
    "Question_Number", "Question_Type", "Question", "Options", "Answer",
    "AACSB", "AICPA", "Bloom's", "Difficulty", "Learning Objective", "Topic",
]

Q_MARKER = re.compile(r"^\s*(\d+)\)\s")
ANSWER_LINE = re.compile(r"^\s*Answer:\s", re.IGNORECASE)
HEADER_QUESTION_MARKER = "Intermediate Accounting, 9e (Spiceland)"

INTERESTING_CODEPOINTS = {
    "–": "EN_DASH",
    "—": "EM_DASH",
    "―": "HORIZONTAL_BAR",
    "‘": "LEFT_SINGLE_QUOTE",
    "’": "RIGHT_SINGLE_QUOTE",
    "“": "LEFT_DOUBLE_QUOTE",
    "”": "RIGHT_DOUBLE_QUOTE",
    " ": "NBSP",
    "�": "REPLACEMENT_CHAR",
    "…": "ELLIPSIS",
    "×": "MULTIPLICATION_SIGN",
    "÷": "DIVISION_SIGN",
    "±": "PLUS_MINUS",
    "©": "COPYRIGHT",
    "®": "REGISTERED",
}


def chapters() -> list[str]:
    return [f"{i:02d}" for i in range(1, 22)]


def find_one(directory: Path, chapter: str, ext: str) -> Path:
    candidates = [p for p in directory.iterdir()
                  if p.suffix == ext
                  and not p.name.startswith("~$")
                  and f"Chapter{chapter}" in p.name]
    if len(candidates) != 1:
        raise RuntimeError(f"{ext} chapter {chapter}: found {candidates}")
    return candidates[0]


def overlap_ratio(a: str, b: str) -> float:
    """Char-set Jaccard. Cheap proxy for Diana's 80% bleed-through rule."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def audit_excel(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return {"error": "empty workbook"}

    header = list(rows[0])
    data = rows[1:]

    schema_match = header == EXPECTED_COLUMNS

    # Row classification
    n_header_artifacts = 0
    n_blank_rows = 0
    n_real_questions = 0
    question_numbers: list[int] = []
    rows_classified: list[tuple[int, str]] = []  # (excel_row_idx_1based, label)
    bloom_counter: Counter[str] = Counter()
    bloom_dual = 0
    qtype_counter: Counter[str] = Counter()
    difficulty_counter: Counter[str] = Counter()
    lo_code_only = 0
    lo_full = 0
    lo_missing = 0
    answer_empty_by_type: Counter[str] = Counter()
    options_bleed_rows: list[tuple[int, float]] = []
    codepoint_counter: Counter[str] = Counter()
    qnum_str_count = 0
    qnum_int_count = 0
    weird_first_rows: list[dict] = []

    for excel_row_idx, raw in enumerate(data, start=2):  # +2 = header + 1-indexed
        row = {col: (raw[i] if i < len(raw) else None) for i, col in enumerate(header)}

        # Inventory non-ASCII codepoints across the row's text
        joined = " ".join(str(v) for v in raw if v is not None)
        for ch in joined:
            if ch in INTERESTING_CODEPOINTS:
                codepoint_counter[INTERESTING_CODEPOINTS[ch]] += 1

        qnum_raw = row.get("Question_Number")
        q_text = (row.get("Question") or "").strip()

        if qnum_raw is None and not q_text:
            n_blank_rows += 1
            rows_classified.append((excel_row_idx, "blank"))
            continue

        # Header artifact: Diana's rule #1
        if str(qnum_raw).strip() == "0" or q_text == HEADER_QUESTION_MARKER:
            n_header_artifacts += 1
            rows_classified.append((excel_row_idx, "header_artifact"))
            if len(weird_first_rows) < 5:
                weird_first_rows.append({
                    "excel_row": excel_row_idx,
                    "qnum": qnum_raw,
                    "question_preview": q_text[:80],
                })
            continue

        # Question-number type sniff
        if isinstance(qnum_raw, str):
            qnum_str_count += 1
        elif isinstance(qnum_raw, int):
            qnum_int_count += 1

        try:
            qnum_int = int(str(qnum_raw).strip())
        except (TypeError, ValueError):
            qnum_int = -1
        if qnum_int >= 1:
            question_numbers.append(qnum_int)

        n_real_questions += 1
        rows_classified.append((excel_row_idx, "question"))

        # Per-question features
        qtype = (row.get("Question_Type") or "").strip()
        qtype_counter[qtype] += 1
        difficulty_counter[(row.get("Difficulty") or "").strip()] += 1

        bloom_raw = (row.get("Bloom's") or "").strip()
        if "; " in bloom_raw:
            bloom_dual += 1
            for label in bloom_raw.split("; "):
                bloom_counter[label.strip()] += 1
        elif bloom_raw:
            bloom_counter[bloom_raw] += 1

        lo_raw = (row.get("Learning Objective") or "").strip()
        if not lo_raw:
            lo_missing += 1
        else:
            # Format: "05-09" alone is code-only; "05-09 Describe..." is full
            tokens = lo_raw.split(None, 1)
            if len(tokens) == 1 and re.match(r"^\d{2}-\d{2}$", tokens[0]):
                lo_code_only += 1
            elif len(tokens) >= 2:
                lo_full += 1
            else:
                lo_missing += 1

        ans = (row.get("Answer") or "").strip()
        if not ans:
            answer_empty_by_type[qtype] += 1

        # Diana's noise rule #5: Essay/Problem with Options text bleeding from Question
        opts = (row.get("Options") or "").strip()
        if qtype == "Essay/Problem" and opts:
            ratio = overlap_ratio(opts, q_text)
            if ratio >= 0.80:
                options_bleed_rows.append((excel_row_idx, round(ratio, 2)))

    # Question-number sequencing
    sorted_q = sorted(question_numbers)
    gaps = []
    if sorted_q:
        expected = list(range(sorted_q[0], sorted_q[-1] + 1))
        seen = set(sorted_q)
        missing = sorted(set(expected) - seen)
        if missing:
            gaps = missing[:20]
    duplicates = [n for n, c in Counter(question_numbers).items() if c > 1]

    return {
        "path": str(path),
        "n_columns": len(header),
        "schema_match": schema_match,
        "header_actual": header,
        "n_data_rows": len(data),
        "n_real_questions": n_real_questions,
        "n_header_artifacts": n_header_artifacts,
        "n_blank_rows": n_blank_rows,
        "qnum_min": sorted_q[0] if sorted_q else None,
        "qnum_max": sorted_q[-1] if sorted_q else None,
        "qnum_gaps_first20": gaps,
        "qnum_duplicates": duplicates,
        "qnum_type_string": qnum_str_count,
        "qnum_type_int": qnum_int_count,
        "bloom_counts": dict(bloom_counter),
        "bloom_dual_label_rows": bloom_dual,
        "qtype_counts": dict(qtype_counter),
        "difficulty_counts": dict(difficulty_counter),
        "lo_code_only": lo_code_only,
        "lo_full_text": lo_full,
        "lo_missing": lo_missing,
        "answer_empty_by_type": dict(answer_empty_by_type),
        "options_bleed_rows_first20": options_bleed_rows[:20],
        "n_options_bleed_rows": len(options_bleed_rows),
        "codepoint_inventory": dict(codepoint_counter),
        "header_artifact_samples": weird_first_rows,
    }


def audit_word(path: Path) -> dict:
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs]
    nonempty = [p for p in paragraphs if p.strip()]

    # "Real" question count = Answer lines (each question has exactly one Answer:).
    n_answer_lines = sum(1 for p in nonempty if ANSWER_LINE.match(p))

    q_starts = [p for p in nonempty if Q_MARKER.match(p)]
    last_qnum = 0
    for p in q_starts:
        m = Q_MARKER.match(p)
        if m:
            last_qnum = max(last_qnum, int(m.group(1)))

    n_tables = len(doc.tables)
    # Table size profile
    table_rows = sum(len(t.rows) for t in doc.tables)
    table_cells = sum(len(r.cells) for t in doc.tables for r in t.rows)

    codepoint_counter: Counter[str] = Counter()
    for p in nonempty:
        for ch in p:
            if ch in INTERESTING_CODEPOINTS:
                codepoint_counter[INTERESTING_CODEPOINTS[ch]] += 1

    return {
        "path": str(path),
        "n_paragraphs_total": len(paragraphs),
        "n_paragraphs_nonempty": len(nonempty),
        "n_question_markers": len(q_starts),
        "n_answer_lines": n_answer_lines,
        "qnum_max_seen": last_qnum,
        "n_tables": n_tables,
        "table_total_rows": table_rows,
        "table_total_cells": table_cells,
        "codepoint_inventory": dict(codepoint_counter),
    }


def table_preservation_probe(word_path: Path, excel_path: Path) -> dict:
    """Sample up to 3 Word tables and check whether their content appears
    in the Excel Answer column of any row. Returns a yes/no per probe."""
    doc = Document(str(word_path))
    if not doc.tables:
        return {"probed": 0, "results": []}

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    answers = []
    for raw in ws.iter_rows(values_only=True, min_row=2):
        # Answer is column index 4 (Question_Number, Type, Question, Options, Answer)
        if len(raw) >= 5 and raw[4]:
            answers.append(str(raw[4]))
    wb.close()
    all_answers = "\n".join(answers)

    results = []
    # Sample first, middle, last table
    n = len(doc.tables)
    sample_idxs = sorted(set([0, n // 2, n - 1]))
    for idx in sample_idxs:
        t = doc.tables[idx]
        cells_text = []
        for r in t.rows:
            for c in r.cells:
                txt = c.text.strip()
                if txt:
                    cells_text.append(txt)
        if not cells_text:
            results.append({"table_idx": idx, "probe": "EMPTY_TABLE", "matched": None})
            continue
        # Use the longest cell content as the probe — most distinctive
        probe = max(cells_text, key=len)
        # Truncate probe to a reasonable length for substring search
        probe_short = probe[:80]
        matched = probe_short in all_answers
        results.append({
            "table_idx": idx,
            "table_rows": len(t.rows),
            "probe_preview": probe_short[:80],
            "matched_in_excel": matched,
        })
    return {"probed": len(results), "n_tables_total": n, "results": results}


def main() -> None:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapters": {},
        "totals": {},
    }

    grand_excel_rows = 0
    grand_real_questions = 0
    grand_header_artifacts = 0
    grand_word_answers = 0
    grand_lo_code_only = 0
    grand_lo_full = 0
    grand_bleed = 0
    grand_dual_bloom = 0
    grand_tables = 0
    table_preserved = 0
    table_lost = 0

    for ch in chapters():
        try:
            xlsx = find_one(EXCEL_DIR, ch, ".xlsx")
            docx = find_one(WORD_DIR, ch, ".docx")
        except RuntimeError as e:
            report["chapters"][ch] = {"error": str(e)}
            continue

        print(f"[ch{ch}] excel + word ...", flush=True)
        ex = audit_excel(xlsx)
        wd = audit_word(docx)
        tp = table_preservation_probe(docx, xlsx)

        delta = ex.get("n_real_questions", 0) - wd.get("n_answer_lines", 0)

        report["chapters"][ch] = {
            "excel": ex,
            "word": wd,
            "table_probe": tp,
            "delta_excel_vs_word_answers": delta,
        }

        grand_excel_rows += ex.get("n_data_rows", 0)
        grand_real_questions += ex.get("n_real_questions", 0)
        grand_header_artifacts += ex.get("n_header_artifacts", 0)
        grand_word_answers += wd.get("n_answer_lines", 0)
        grand_lo_code_only += ex.get("lo_code_only", 0)
        grand_lo_full += ex.get("lo_full_text", 0)
        grand_bleed += ex.get("n_options_bleed_rows", 0)
        grand_dual_bloom += ex.get("bloom_dual_label_rows", 0)
        grand_tables += wd.get("n_tables", 0)
        for r in tp.get("results", []):
            if r.get("matched_in_excel") is True:
                table_preserved += 1
            elif r.get("matched_in_excel") is False:
                table_lost += 1

    report["totals"] = {
        "excel_data_rows_all_chapters": grand_excel_rows,
        "excel_real_questions_all_chapters": grand_real_questions,
        "excel_header_artifact_rows": grand_header_artifacts,
        "word_answer_lines_all_chapters": grand_word_answers,
        "delta_real_vs_word_answers": grand_real_questions - grand_word_answers,
        "lo_code_only_rows": grand_lo_code_only,
        "lo_full_text_rows": grand_lo_full,
        "options_bleed_rows": grand_bleed,
        "bloom_dual_label_rows": grand_dual_bloom,
        "word_tables_total": grand_tables,
        "table_probe_preserved": table_preserved,
        "table_probe_lost": table_lost,
    }

    json_path = OUT_DIR / "audit_report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {json_path}")

    # Markdown summary
    md = [
        "# Spiceland 9e Excel-vs-Word audit",
        "",
        f"_Generated: {report['generated_at']}_",
        "",
        "## Totals across all 21 chapters",
        "",
        f"- Excel rows total: **{grand_excel_rows:,}**",
        f"- Header-artifact rows (drop on ingest): **{grand_header_artifacts}**",
        f"- Real-question rows in Excel: **{grand_real_questions:,}**",
        f"- Word answer-lines (canonical question count): **{grand_word_answers:,}**",
        f"- Delta (Excel real vs Word answers): **{grand_real_questions - grand_word_answers:+d}**",
        f"- LO code-only rows (need Word fallback for full text): **{grand_lo_code_only:,}**",
        f"- LO full-text rows: **{grand_lo_full:,}**",
        f"- Options-column bleed-through rows: **{grand_bleed}**",
        f"- Bloom dual-label rows: **{grand_dual_bloom}**",
        f"- Word tables total (JEs, schedules, etc.): **{grand_tables:,}**",
        f"- Table-content probe: preserved in Excel **{table_preserved}** / lost **{table_lost}**",
        "",
        "## Per-chapter row reconciliation",
        "",
        "| Ch | Excel rows | Headers | Real q | Word answers | Δ | LO code-only | LO full | Bleed | Dual Bloom | Tables | Tables preserved |",
        "|----|------------|---------|--------|--------------|---|--------------|---------|-------|------------|--------|------------------|",
    ]
    for ch in chapters():
        d = report["chapters"].get(ch, {})
        if "error" in d:
            md.append(f"| {ch} | ERROR | | | | | | | | | | |")
            continue
        ex, wd, tp = d["excel"], d["word"], d["table_probe"]
        preserved = sum(1 for r in tp["results"] if r.get("matched_in_excel") is True)
        probed = len([r for r in tp["results"] if r.get("matched_in_excel") is not None])
        md.append(
            f"| {ch} | {ex['n_data_rows']} | {ex['n_header_artifacts']} | {ex['n_real_questions']} | "
            f"{wd['n_answer_lines']} | {d['delta_excel_vs_word_answers']:+d} | "
            f"{ex['lo_code_only']} | {ex['lo_full_text']} | {ex['n_options_bleed_rows']} | "
            f"{ex['bloom_dual_label_rows']} | {wd['n_tables']} | {preserved}/{probed} |"
        )

    md += [
        "",
        "## Codepoint inventory (Excel, all chapters)",
        "",
        "| Codepoint | Total occurrences |",
        "|-----------|-------------------|",
    ]
    grand_cp: Counter[str] = Counter()
    for ch in chapters():
        d = report["chapters"].get(ch, {})
        if "error" in d:
            continue
        for k, v in d["excel"].get("codepoint_inventory", {}).items():
            grand_cp[k] += v
    for k, v in sorted(grand_cp.items(), key=lambda x: -x[1]):
        md.append(f"| {k} | {v:,} |")

    md += [
        "",
        "## Schema check (Excel)",
        "",
        "| Ch | n_columns | schema_match |",
        "|----|-----------|--------------|",
    ]
    for ch in chapters():
        d = report["chapters"].get(ch, {})
        if "error" in d:
            md.append(f"| {ch} | ERROR | |")
            continue
        ex = d["excel"]
        md.append(f"| {ch} | {ex['n_columns']} | {'YES' if ex['schema_match'] else 'NO'} |")

    # Question-number sequencing
    md += [
        "",
        "## Question-number gaps and duplicates (Excel)",
        "",
        "| Ch | min | max | gaps (first 20) | duplicates |",
        "|----|-----|-----|-----------------|------------|",
    ]
    for ch in chapters():
        d = report["chapters"].get(ch, {})
        if "error" in d:
            md.append(f"| {ch} | ERROR | | | |")
            continue
        ex = d["excel"]
        gaps_str = ", ".join(str(g) for g in ex.get("qnum_gaps_first20", [])) or "—"
        dups_str = ", ".join(str(g) for g in ex.get("qnum_duplicates", [])) or "—"
        md.append(f"| {ch} | {ex.get('qnum_min')} | {ex.get('qnum_max')} | {gaps_str} | {dups_str} |")

    md_path = OUT_DIR / "audit_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {md_path}")

    print("\n=== SUMMARY ===")
    print(json.dumps(report["totals"], indent=2))


if __name__ == "__main__":
    main()
