"""Canonical ingest: Spiceland 9e Excel + Word → eval/spiceland9e.jsonl.

Applies every noise rule discovered during the data-quality audit:

  1. Drop header artifacts (Question_Number == 0, or Question == publisher
     header marker).
  2. Dual Bloom / AICPA label split on '; '.
  3. ID disambiguation by Question_Type (collisions in ch05, ch09).
  4. Ch.08-09 Bloom column swap — when Bloom's contains AICPA-shaped
     content and Blooms (no apostrophe) holds the real Bloom level, swap.
  5. Word fallback for LO text when Excel only has the code.
  6. Word fallback for Answer when Excel Essay/Problem Answer is empty.
  7. Strip metadata bleed-through ('Difficulty:', 'Topic:', etc.) from
     Excel Explanation cells.
  8. Options column bleed-through (Essay/Problem with Options text ≈ Question
     text) → Options = null.
  9. Multi-part fragment detection — short Question, missing metadata,
     duplicate Q# → log, do not drop.
 10. Attach Word tables (eval/spiceland9e_tables.jsonl) by parent_question_id.

Idempotent: byte-identical output across runs given byte-identical inputs.

Outputs:
  eval/spiceland9e.jsonl                          one record per question
  eval/stats/run_{YYYYMMDD_HHMMSS}.json           per-run stats
  eval/diana_warnings.log                         human-readable warning log

Run from repo root:
  python eval/ingest_spiceland.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "data" / "Intermediate Financial Accounting test bank"
EXCEL_DIR = SRC / "excel"
WORD_DIR = SRC / "word"
OUT_JSONL = REPO_ROOT / "eval" / "spiceland9e.jsonl"
STATS_DIR = REPO_ROOT / "eval" / "stats"
WARNINGS_LOG = REPO_ROOT / "eval" / "diana_warnings.log"
TABLES_JSONL = REPO_ROOT / "eval" / "spiceland9e_tables.jsonl"

STATS_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

HEADER_QUESTION_MARKER = "Intermediate Accounting, 9e (Spiceland)"
Q_MARKER = re.compile(r"^\s*(\d+)\)(\s|$)")
LO_PARA = re.compile(r"^\s*Learning Objective:\s*(\d{2}-\d{2})(?:\s+(.+))?$", re.IGNORECASE)
ANSWER_PARA = re.compile(r"^\s*Answer:\s*(.+)?$", re.IGNORECASE)
EXPLANATION_PARA = re.compile(r"^\s*Explanation:\s*(.*)$", re.IGNORECASE)
META_PARA = re.compile(
    r"^\s*(Difficulty|Topic|Learning Objective|Bloom['’]?s|AACSB|AICPA|"
    r"Accessible/AICPA|Question Type)\s*:",
    re.IGNORECASE,
)
LO_FIELD_CODE_ONLY = re.compile(r"^\s*\d{2}-\d{2}\s*$")
AICPA_LIKE_IN_BLOOM = re.compile(r"\b(BB|FN|AC)\b\s", re.IGNORECASE)
EXPLANATION_BLEED_PREFIXES = (
    "Difficulty:", "Topic:", "Learning Objective:", "Bloom's:", "Blooms:",
    "AACSB:", "AICPA:", "Accessible/AICPA:", "Question_Type:", "Question Type:",
)

TYPE_TO_SUFFIX = {
    "Multiple Choice": "mc",
    "True/False": "tf",
    "Matching": "ma",
    "Essay/Problem": "es",
}


# ============================================================================
# Word fallback parser
# ============================================================================

def iter_block_items(parent):
    if isinstance(parent, _Document):
        elm = parent.element.body
    elif isinstance(parent, _Cell):
        elm = parent._tc
    else:
        raise TypeError(type(parent))
    for child in elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def parse_word_metadata(path: Path) -> dict[int, dict]:
    """Build {qnum: {'lo_code', 'lo_text', 'answer_text', 'explanation_text'}}
    from a Word .docx.

    Walks body in document order, tracks the current question number, and
    captures: 'Learning Objective:', 'Answer:', and any paragraphs that
    follow 'Answer:' until the next metadata line (Difficulty:, Topic:, etc.)
    or the next question. Those post-Answer paragraphs are the rationale /
    worked solution that the Excel Explanation column may be missing —
    especially for Ch.01-05 which have no Explanation column at all.

    Q# only advances on monotonic increase (matches the table-extractor
    heuristic), to skip in-question enumerations like "1) first step...".
    """
    doc = Document(str(path))
    out: dict[int, dict] = defaultdict(dict)
    current_q: int | None = None
    in_explanation = False  # True between "Answer:" and the next metadata line
    explanation_buf: list[str] = []

    def flush_explanation() -> None:
        nonlocal explanation_buf
        if current_q is not None and explanation_buf:
            text = "\n".join(explanation_buf).strip()
            if text:
                out[current_q].setdefault("explanation_text", text)
        explanation_buf = []

    for block in iter_block_items(doc):
        if not isinstance(block, Paragraph):
            continue
        text = block.text.strip()
        if not text:
            continue
        m = Q_MARKER.match(text)
        if m:
            n = int(m.group(1))
            if current_q is None or n > current_q:
                # Question boundary — flush any pending explanation, advance.
                flush_explanation()
                in_explanation = False
                current_q = n
                continue
            # In-question enumeration: keep accumulating if we're inside an
            # explanation block (the rationale might contain enumerated steps).
            if in_explanation:
                explanation_buf.append(text)
                continue
            continue
        if current_q is None:
            continue
        # Metadata line ends the explanation block
        if META_PARA.match(text):
            flush_explanation()
            in_explanation = False
            # Still capture the LO line via the LO regex below.
            m_lo = LO_PARA.match(text)
            if m_lo:
                code = m_lo.group(1)
                lo_text = (m_lo.group(2) or "").strip()
                out[current_q].setdefault("lo_code", code)
                if lo_text:
                    out[current_q].setdefault("lo_text", lo_text)
            continue
        m_ans = ANSWER_PARA.match(text)
        if m_ans:
            answer_payload = (m_ans.group(1) or "").strip()
            out[current_q].setdefault("answer_text", answer_payload)
            in_explanation = True
            explanation_buf = []
            continue
        if in_explanation:
            # Strip a leading "Explanation:" prefix from the first paragraph
            # so the stored text starts with the actual rationale.
            m_expl = EXPLANATION_PARA.match(text)
            if m_expl:
                payload = m_expl.group(1).strip()
                if payload:
                    explanation_buf.append(payload)
            else:
                explanation_buf.append(text)
            continue
    # End-of-doc flush
    flush_explanation()
    return dict(out)


# ============================================================================
# Tables index
# ============================================================================

def load_tables_index() -> dict[tuple[int, int], list[dict]]:
    """Group spiceland9e_tables.jsonl by (chapter, question_number)."""
    if not TABLES_JSONL.exists():
        return {}
    idx: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for line in TABLES_JSONL.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("question_number") is None:
            continue
        idx[(r["chapter"], r["question_number"])].append(r)
    # Stable order within each question
    for k in idx:
        idx[k].sort(key=lambda x: x["table_idx_under_question"])
    return dict(idx)


# ============================================================================
# Field-level helpers
# ============================================================================

def split_multilabel(val: str | None, sep: str = "; ") -> list[str]:
    if not val or not val.strip():
        return []
    return [t.strip() for t in val.split(sep) if t.strip()]


def to_int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_options_cell(opts: str | None) -> list[str]:
    """Parse Excel Options cell. Spiceland's canonical format is
    'A: text | B: text | C: text | D: text'. Fall back to other patterns."""
    if not opts:
        return []
    s = opts.strip()
    if not s:
        return []
    # Pattern 1 (most common): 'A: ... | B: ... | C: ... | D: ...'
    if "|" in s and re.search(r"\b[A-Z]:", s):
        parts = re.split(r"\s*\|\s*", s)
        return [p.strip() for p in parts if p.strip()]
    # Pattern 2: newline-separated
    if "\n" in s:
        return [p.strip() for p in s.split("\n") if p.strip()]
    # Pattern 3: no separator, split on lettered markers
    if re.search(r"\b[A-Z][:)]", s):
        parts = re.split(r"(?=\b[A-Z][:)])", s)
        return [p.strip() for p in parts if p.strip()]
    return [s]


def lo_field_parse(raw: str | None) -> tuple[str | None, str | None]:
    """Excel LO cell → (code, text). Returns (None, None) if empty.
    'code-only' rows return (code, None) so a Word fallback can fill text."""
    if not raw or not str(raw).strip():
        return None, None
    s = str(raw).strip()
    if LO_FIELD_CODE_ONLY.match(s):
        return s, None
    m = re.match(r"^(\d{2}-\d{2})\s+(.+)$", s)
    if m:
        return m.group(1), m.group(2).strip()
    return None, s  # text-only without code; rare


def clean_explanation(expl: str | None) -> tuple[str | None, list[str]]:
    """Strip trailing-line metadata bleed-through from Excel Explanation.
    Returns (cleaned_text or None, list of bled-prefixes seen)."""
    if not expl:
        return None, []
    lines = [ln.rstrip() for ln in expl.split("\n")]
    kept: list[str] = []
    bled: list[str] = []
    for ln in lines:
        stripped = ln.lstrip()
        matched = False
        for pref in EXPLANATION_BLEED_PREFIXES:
            if stripped.startswith(pref):
                bled.append(pref.rstrip(":"))
                matched = True
                break
        if not matched:
            kept.append(ln)
    cleaned = "\n".join(kept).strip()
    return (cleaned or None), bled


def resolve_bloom(blooms_apostrophe: str | None,
                  blooms_no_apostrophe: str | None) -> tuple[str, str | None]:
    """Resolve the Bloom level given Excel's two Bloom columns.

    Ch.08-09 carry a second 'Blooms' column (no apostrophe). Observed pattern:
    in ~10 rows per chapter, Bloom's is empty and Blooms holds the actual
    level. Where both are populated and disagree, prefer Bloom's (the
    canonical column) and emit a warning.

    Returns (bloom_value, warning or None).
    """
    a = (blooms_apostrophe or "").strip()
    b = (blooms_no_apostrophe or "").strip()
    if a and b and a != b:
        return a, f"Bloom's={a!r} disagrees with Blooms={b!r}; using Bloom's"
    if a:
        return a, None
    if b:
        return b, "Bloom's empty, used Blooms fallback"
    return "", None


def overlap_ratio(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def is_fragment(prompt: str, bloom: list[str], diff: str | None, lo_code: str | None) -> bool:
    metadata_missing = sum(1 for v in (bloom, diff, lo_code) if not v)
    return (len(prompt) < 40) and metadata_missing >= 2


# ============================================================================
# Per-chapter ingest
# ============================================================================

def find_one(directory: Path, chapter: str, ext: str) -> Path:
    matches = [p for p in directory.iterdir()
               if p.suffix == ext and not p.name.startswith("~$")
               and f"Chapter{chapter}" in p.name]
    if len(matches) != 1:
        raise RuntimeError(f"chapter {chapter} {ext}: {matches}")
    return matches[0]


def ingest_chapter(chapter: str, tables_idx: dict, warnings_out: list) -> tuple[list[dict], dict]:
    chapter_int = int(chapter)
    xlsx_path = find_one(EXCEL_DIR, chapter, ".xlsx")
    docx_path = find_one(WORD_DIR, chapter, ".docx")

    # Pre-parse Word for LO + Answer fallback (third-tier; Excel-internal lookup is first)
    word_meta = parse_word_metadata(docx_path)

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header = list(rows[0])
    data = rows[1:]

    # First pass: build chapter-internal LO code → text map from rows whose
    # Excel cell carries the full 'NN-NN Text...' form. This recovers LO text
    # for the code-only rows from sibling rows in the same workbook — more
    # robust than the Word fallback because Spiceland's Word doc sometimes
    # omits 'Learning Objective:' lines for Essay/Problem questions.
    lo_text_by_code: dict[str, str] = {}
    lo_idx_local = header.index("Learning Objective") if "Learning Objective" in header else None
    if lo_idx_local is not None:
        for raw in data:
            v = raw[lo_idx_local] if lo_idx_local < len(raw) else None
            if not v or not isinstance(v, str):
                continue
            code, text = lo_field_parse(v)
            if code and text:
                lo_text_by_code.setdefault(code, text)

    # Resolve col indices safely (schema varies across chapters)
    def col(name: str) -> int | None:
        return header.index(name) if name in header else None

    idx_qnum = col("Question_Number")
    idx_qtype = col("Question_Type")
    idx_q = col("Question")
    idx_opts = col("Options")
    idx_ans = col("Answer")
    idx_expl = col("Explanation")  # may be None for ch.01-05
    idx_aacsb = col("AACSB")
    idx_aicpa = col("AICPA")
    idx_bloom = col("Bloom's")
    idx_blooms_alt = col("Blooms")  # ch.08-09 only
    idx_diff = col("Difficulty")
    idx_lo = col("Learning Objective")
    idx_topic = col("Topic")

    records: list[dict] = []
    seen_ids: Counter = Counter()
    stats = Counter()

    for excel_row_idx, raw in enumerate(data, start=2):
        cell = lambda i: raw[i] if i is not None and i < len(raw) else None

        qnum_raw = cell(idx_qnum)
        q_text = (cell(idx_q) or "")
        if isinstance(q_text, str):
            q_text = q_text.strip()
        else:
            q_text = str(q_text).strip() if q_text is not None else ""

        # Noise rule #1: header artifacts
        if str(qnum_raw or "").strip() == "0" or q_text == HEADER_QUESTION_MARKER:
            stats["header_artifact_dropped"] += 1
            continue

        qnum = to_int_or_none(qnum_raw)
        if qnum is None:
            stats["row_skipped_no_qnum"] += 1
            warnings_out.append(f"ch{chapter} row{excel_row_idx}: missing/unparseable Question_Number")
            continue

        qtype = (cell(idx_qtype) or "").strip() if cell(idx_qtype) else ""

        # Reclassify: rows tagged 'Multiple Choice' whose Answer cell is a
        # long-form worked solution (not a single letter) are actually
        # Essay/Problem questions that were mistyped in the Excel.
        # Detection: Answer is non-letter AND has substantial length.
        ans_for_reclass = cell(idx_ans)
        ans_for_reclass_s = (
            str(ans_for_reclass).strip() if ans_for_reclass is not None else ""
        )
        if qtype == "Multiple Choice" and ans_for_reclass_s:
            looks_like_letter = (
                len(ans_for_reclass_s) <= 2 and ans_for_reclass_s[0].isalpha()
            )
            if not looks_like_letter and (
                len(ans_for_reclass_s) > 200 or "\n" in ans_for_reclass_s
            ):
                stats["mc_mislabel_reclassified_to_essay"] += 1
                warnings_out.append(
                    f"ch{chapter} row{excel_row_idx}: 'Multiple Choice' with "
                    f"non-letter Answer (len={len(ans_for_reclass_s)}); "
                    f"reclassified to 'Essay/Problem'"
                )
                qtype = "Essay/Problem"

        prompt = q_text

        # Strip the "N) " prefix from prompt if present — keeps prompt clean
        m_prefix = re.match(rf"^\s*{qnum}\)\s*(.*)$", prompt, re.DOTALL)
        prompt_clean = m_prefix.group(1).strip() if m_prefix else prompt

        # Options
        options = parse_options_cell(cell(idx_opts))

        # Noise rule #8: Options bleed-through (Essay/Problem with Options ≈ Question)
        opts_str = (cell(idx_opts) or "").strip() if cell(idx_opts) else ""
        if qtype == "Essay/Problem" and opts_str:
            if overlap_ratio(opts_str, prompt) >= 0.80:
                options = []
                stats["options_bleed_dropped"] += 1
                warnings_out.append(
                    f"ch{chapter} row{excel_row_idx}: Options-bleed (overlap≥0.80), Options set to null"
                )

        # Answer (Excel-canonical, with Word fallback for empty Essay/Problem)
        answer_raw = cell(idx_ans)
        answer = "" if answer_raw is None else str(answer_raw).strip()
        if not answer and qtype == "Essay/Problem":
            wa = word_meta.get(qnum, {}).get("answer_text")
            if wa:
                answer = wa
                stats["answer_word_fallback"] += 1
                warnings_out.append(
                    f"ch{chapter} row{excel_row_idx}: Essay Answer empty in Excel, filled from Word"
                )
            else:
                stats["answer_empty"] += 1
                warnings_out.append(
                    f"ch{chapter} row{excel_row_idx}: Essay Answer empty in BOTH Excel and Word"
                )

        # Explanation (worked solution) — Excel first, Word fallback.
        # Excel `Explanation` column exists only in Ch.06-21; for Ch.01-05
        # AND for any Ch.06-21 row where Excel Explanation is empty, fall
        # back to the post-Answer 'Explanation:' paragraphs from Word.
        explanation = None
        if idx_expl is not None:
            expl_raw = cell(idx_expl)
            cleaned, bled = clean_explanation(expl_raw if isinstance(expl_raw, str) else None)
            explanation = cleaned
            if bled:
                stats["explanation_metadata_stripped"] += 1
                warnings_out.append(
                    f"ch{chapter} row{excel_row_idx}: stripped Explanation bleed ({','.join(bled)})"
                )
        if not explanation:
            word_expl = word_meta.get(qnum, {}).get("explanation_text")
            if word_expl:
                explanation = word_expl
                stats["explanation_word_fallback"] += 1

        # Bloom (with ch.08/09 second-column fallback)
        bloom_raw = cell(idx_bloom)
        bloom_alt = cell(idx_blooms_alt) if idx_blooms_alt is not None else None
        bloom_apostrophe_str = (bloom_raw or "").strip() if isinstance(bloom_raw, str) else (str(bloom_raw).strip() if bloom_raw is not None else "")
        bloom_alt_str = (bloom_alt or "").strip() if isinstance(bloom_alt, str) else (str(bloom_alt).strip() if bloom_alt is not None else "")
        bloom_value, bloom_warning = resolve_bloom(bloom_apostrophe_str, bloom_alt_str)
        if bloom_warning:
            stats["bloom_fallback_or_disagreement"] += 1
            warnings_out.append(f"ch{chapter} row{excel_row_idx}: {bloom_warning}")
        bloom = split_multilabel(bloom_value)
        stats["bloom_dual_label"] += 1 if len(bloom) > 1 else 0

        # AICPA
        aicpa_raw = cell(idx_aicpa)
        aicpa_str = (aicpa_raw or "").strip() if isinstance(aicpa_raw, str) else (str(aicpa_raw).strip() if aicpa_raw is not None else "")
        aicpa = split_multilabel(aicpa_str)

        # Difficulty / AACSB / Topic
        difficulty = (cell(idx_diff) or "").strip() if cell(idx_diff) else None
        aacsb = (cell(idx_aacsb) or "").strip() if cell(idx_aacsb) else None
        topic = (cell(idx_topic) or "").strip() if cell(idx_topic) else None

        # Learning Objective: code-only Excel rows get text from an Excel-
        # internal code→text map first, Word as last resort.
        lo_code, lo_text = lo_field_parse(cell(idx_lo))
        if lo_code and not lo_text:
            if lo_code in lo_text_by_code:
                lo_text = lo_text_by_code[lo_code]
                stats["lo_excel_internal_fallback"] += 1
            else:
                wm = word_meta.get(qnum, {})
                if wm.get("lo_text"):
                    lo_text = wm["lo_text"]
                    stats["lo_word_fallback"] += 1
                else:
                    stats["lo_text_unrecoverable"] += 1
                    warnings_out.append(
                        f"ch{chapter} row{excel_row_idx}: LO code '{lo_code}' "
                        f"has no text in Excel or Word"
                    )

        # Fragment detection (noise rule #9)
        if is_fragment(prompt_clean, bloom, difficulty, lo_code):
            stats["fragment_detected"] += 1
            warnings_out.append(
                f"ch{chapter} row{excel_row_idx}: fragment row (short prompt, missing metadata)"
            )

        # ID with disambiguation
        suffix = TYPE_TO_SUFFIX.get(qtype, "xx")
        base_id = f"ch{chapter_int:02d}_q{qnum:04d}_{suffix}"
        seen_ids[base_id] += 1
        if seen_ids[base_id] > 1:
            this_id = f"{base_id}_dup{seen_ids[base_id]-1:02d}"
            stats["id_collision_disambiguated"] += 1
            warnings_out.append(
                f"ch{chapter} row{excel_row_idx}: id collision on {base_id}; assigned {this_id}"
            )
        else:
            this_id = base_id

        # Attach tables
        tables_for_q = [
            {k: v for k, v in t.items() if k not in {"cells"}}  # drop raw cells; keep markdown
            for t in tables_idx.get((chapter_int, qnum), [])
        ]
        if tables_for_q:
            stats["records_with_tables"] += 1
            stats["tables_attached"] += len(tables_for_q)

        rec = {
            "id": this_id,
            "chapter": chapter_int,
            "question_number": qnum,
            "type": qtype or None,
            "prompt": prompt_clean,
            "options": options,
            "gold_answer": answer or None,
            "explanation": explanation,
            "bloom": bloom,
            "difficulty": difficulty,
            "lo": {"code": lo_code, "text": lo_text} if (lo_code or lo_text) else None,
            "topic": topic,
            "aacsb": aacsb,
            "aicpa": aicpa,
            "tables": tables_for_q,
            "source_workbook": xlsx_path.name,
            "source_row": excel_row_idx,
        }
        records.append(rec)
        stats["records_emitted"] += 1

    return records, dict(stats)


# ============================================================================
# Driver
# ============================================================================

def main() -> None:
    print("Loading tables index ...", flush=True)
    tables_idx = load_tables_index()
    print(f"  {sum(len(v) for v in tables_idx.values())} tables across "
          f"{len(tables_idx)} (chapter, question) keys", flush=True)

    all_records: list[dict] = []
    all_stats: Counter = Counter()
    per_chapter: dict[str, dict] = {}
    warnings: list[str] = []

    for i in range(1, 22):
        ch = f"{i:02d}"
        print(f"[ch{ch}] ingesting ...", flush=True)
        records, stats = ingest_chapter(ch, tables_idx, warnings)
        per_chapter[ch] = stats
        for k, v in stats.items():
            all_stats[k] += v
        all_records.extend(records)

    # Deterministic sort: (chapter, qnum, type-suffix, source_row)
    all_records.sort(key=lambda r: (
        r["chapter"], r["question_number"],
        TYPE_TO_SUFFIX.get(r["type"] or "", "zz"),
        r["source_row"],
    ))

    # Write JSONL with stable JSON serialization
    with OUT_JSONL.open("w", encoding="utf-8", newline="\n") as fh:
        for r in all_records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            fh.write("\n")

    jsonl_bytes = OUT_JSONL.read_bytes()
    jsonl_sha = hashlib.sha256(jsonl_bytes).hexdigest()
    print(f"\nwrote {OUT_JSONL}  ({len(all_records):,} records, "
          f"{len(jsonl_bytes):,} bytes, sha256={jsonl_sha[:16]}…)")

    # Write warnings
    WARNINGS_LOG.write_text("\n".join(warnings) + "\n" if warnings else "", encoding="utf-8")
    print(f"wrote {WARNINGS_LOG}  ({len(warnings):,} warnings)")

    # Write stats
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stats_path = STATS_DIR / f"run_{ts}.json"
    stats_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(all_records),
        "jsonl_sha256": jsonl_sha,
        "jsonl_bytes": len(jsonl_bytes),
        "totals": dict(all_stats),
        "per_chapter": per_chapter,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {stats_path}")

    print("\n=== TOTALS ===")
    for k, v in sorted(all_stats.items(), key=lambda x: -x[1]):
        print(f"  {k:40s} {v:,}")


if __name__ == "__main__":
    main()
