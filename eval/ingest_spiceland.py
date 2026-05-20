"""Canonical ingest: Spiceland 9e Excel + Word → eval/spiceland9e.jsonl.

Applies every noise rule discovered during the data-quality audit, plus
the v1.1.0 additions (Carla's GAAP-divergence catalog, AACSB
canonicalization, standards-version smell triggers, gold-status, and
the two empty-answer resolutions for ch12_q0199 / ch21_q0141).

  1. Drop header artifacts (Question_Number == 0, or Question == publisher
     header marker).
  2. Dual Bloom / AICPA / AACSB label split on '; ' and ', '.
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
 11. v1.1.0 meta block: gaap_divergence + asc_anchor + gaap_supersession +
     standards_smell + gold_status + exclude_from_scoring.
 12. v1.1.0 ch12_q0199 recovered gold (from table per Carla 2026-05-20).
 13. v1.1.0 ch21_q0141 publisher-ambiguous, exclude_from_scoring=true.

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

SCHEMA_VERSION = "spiceland9e-v1.1.0"

# ============================================================================
# v1.1.0 — AACSB canonicalization (51 raw variants → ≤ 15 canonical labels)
# ============================================================================
# The published Spiceland AACSB tag set is small; the raw 51 variants are
# delimiter noise (', ' vs '; '), ordering noise, and three typos. Apply the
# same multilabel discipline as AICPA: split, normalize, dedupe, sort.

AACSB_TYPO_MAP = {
    "analytic": "Analytical Thinking",
    "analytical": "Analytical Thinking",
    "communicative": "Communication",
    "knowledge application": "Knowledge Application",
    "critical thinking": "Reflective Thinking",
    "resource management": "Knowledge Application",
}

AACSB_CANONICAL_LIST = (
    "Analytical Thinking",
    "Communication",
    "Diversity",
    "Ethics",
    "Knowledge Application",
    "Reflective Thinking",
    "Technology",
)


def canonicalize_aacsb_token(tok: str) -> str | None:
    t = tok.strip()
    if not t:
        return None
    key = t.lower()
    if key in AACSB_TYPO_MAP:
        return AACSB_TYPO_MAP[key]
    # Title-case each whitespace-separated word so "knowledge application"
    # becomes "Knowledge Application".
    return " ".join(w.capitalize() for w in t.split())


def canonicalize_aacsb(raw: str | None) -> list[str]:
    """Split on '; ' or ', ', canonicalize, dedupe, sort alphabetically.

    Mirrors the AICPA multilabel split (`split_multilabel`) but with the
    AACSB-specific typo map and case folding. Returns [] for None/empty.
    """
    if not raw:
        return []
    s = raw.strip()
    if not s:
        return []
    # Spiceland uses both '; ' and ', '. Split on either.
    tokens = re.split(r"\s*[;,]\s*", s)
    canonical: set[str] = set()
    for tok in tokens:
        c = canonicalize_aacsb_token(tok)
        if c:
            canonical.add(c)
    return sorted(canonical)


# ============================================================================
# v1.1.0 — Carla's GAAP-divergence catalog (drift slice)
# ============================================================================
# Plan §2 — case-insensitive substring matching on topic + lo.number + prompt.
# Each filter returns (asc_anchor, modern_answer_hint, drift_topic_id).

CECL_TOPIC_KEYWORDS = (
    "uncollectible",
    "receivable",
    "bad debt",
    "allowance",
    "notes receivable",
    "impairment of a receivable",
    "troubled debt restructuring",
)
CECL_CH7_LOS = {"07-04", "07-05", "07-06", "07-07"}
CECL_CH12_LOS = {"12-08"}

CONVERTIBLES_CH14_TOPIC_KEYWORDS = (
    "convertible",
    "induced conversion",
    "beneficial conversion",
)
CONVERTIBLES_CH19_TOPIC_KEYWORDS = (
    "diluted eps",
    "if-converted",
    "convertible securities",
)
CONVERTIBLES_PROMPT_KEYWORDS = ("convertible", "if-converted")

GOODWILL_CH11_TOPIC_KEYWORDS = (
    "goodwill",
    "impairment of value ‒ goodwill",
    "impairment of value - goodwill",
)
GOODWILL_CH11_LOS = {"11-08", "11-09"}
GOODWILL_PROMPT_KEYWORDS = ("step 1", "step 2", "implied fair value of goodwill")

TAX_CH16_TOPIC_KEYWORDS = (
    "intraperiod",
    "valuation allowance",
    "rate reconciliation",
    "disclosure",
    "disclosure notes",
    "uncertainty in income taxes",
)
TAX_CH16_LOS = {"16-08", "16-09"}


CECL_NOTE = (
    "Note: per ASU 2016-13 (effective fiscal years beginning after "
    "2022-12-15 for all entities), the incurred-loss model was replaced "
    "by the current expected credit loss (CECL) model requiring lifetime "
    "expected credit losses at origination. Current GAAP: ASC 326-20-30 "
    "(receivables) and ASC 326-30-30 (HTM debt). Spiceland teaching on "
    "the allowance-account mechanism remains correct; the measurement "
    "trigger (\"probable + estimable\" incurred-loss threshold) is "
    "superseded by day-one lifetime ECL."
)

CONVERTIBLES_NOTE = (
    "Note: per ASU 2020-06 (effective public 2022, all others 2024), the "
    "cash-conversion and beneficial-conversion-feature separation models "
    "were eliminated for most convertible debt; instruments are accounted "
    "for as a single liability unless they meet specific bifurcation "
    "criteria. The diluted-EPS if-converted method was also amended. "
    "Current GAAP: ASC 470-20-25 and ASC 260-10-45. Spiceland's "
    "pre-2020-06 separation and BCF allocation is superseded."
)

GOODWILL_NOTE = (
    "Note: per ASU 2017-04 (effective public 2020, private 2023), Step 2 "
    "of the goodwill impairment test was eliminated. Impairment is now "
    "measured directly as the excess of the reporting unit's carrying "
    "amount over its fair value, capped at the goodwill balance. Current "
    "GAAP: ASC 350-20-35. Spiceland's two-step illustration is "
    "superseded; the qualitative assessment (Step 0) and Step 1 trigger "
    "remain correct."
)

TAX_NOTE = (
    "Note: per ASU 2019-12 (simplifications) and ASU 2023-09 "
    "(disclosure), the exception to the incremental approach for "
    "intraperiod allocation was eliminated and disaggregated "
    "rate-reconciliation + income-taxes-paid disclosures were added. "
    "Current GAAP: ASC 740-20-45 and ASC 740-10-50. Spiceland's worked "
    "intraperiod examples invoking the deleted exception are superseded; "
    "deferred-tax-asset/liability mechanics remain correct."
)


def _topic_matches(topic: str | None, keywords: tuple[str, ...]) -> bool:
    if not topic:
        return False
    t = topic.lower()
    return any(k in t for k in keywords)


def _prompt_matches(prompt: str | None, keywords: tuple[str, ...]) -> bool:
    if not prompt:
        return False
    p = prompt.lower()
    return any(k in p for k in keywords)


def detect_drift(chapter: int, lo_code: str | None,
                 topic: str | None, prompt: str | None) -> dict | None:
    """Return drift annotation dict or None. The annotation is the value of
    `meta.gaap_supersession` plus the drift_topic_id used for stats."""
    # 1. CECL — Ch. 7 (+ Ch. 12 HTM subset)
    if chapter == 7:
        topic_hit = _topic_matches(topic, CECL_TOPIC_KEYWORDS)
        lo_hit = lo_code in CECL_CH7_LOS if lo_code else False
        if topic_hit and lo_hit:
            return {
                "drift_topic_id": "CECL",
                "asc_anchor": {"topic": 326, "subtopic": 20, "section": 30},
                "asu_number": "2016-13",
                "effective_date": "2022-12-15",
                "modern_answer_hint": CECL_NOTE,
                "asc_pdf_path": "data/GAAP Data/Assets/326 financial instruments-credit losses.pdf",
            }
    if chapter == 12 and lo_code in CECL_CH12_LOS:
        return {
            "drift_topic_id": "CECL",
            "asc_anchor": {"topic": 326, "subtopic": 30, "section": 30},
            "asu_number": "2016-13",
            "effective_date": "2022-12-15",
            "modern_answer_hint": CECL_NOTE,
            "asc_pdf_path": "data/GAAP Data/Assets/326 financial instruments-credit losses.pdf",
        }

    # 2. Convertibles + diluted EPS — Ch. 14 + Ch. 19
    if chapter == 14:
        if _topic_matches(topic, CONVERTIBLES_CH14_TOPIC_KEYWORDS) or \
                _prompt_matches(prompt, CONVERTIBLES_PROMPT_KEYWORDS):
            return {
                "drift_topic_id": "convertibles",
                "asc_anchor": {"topic": 470, "subtopic": 20, "section": 25},
                "asu_number": "2020-06",
                "effective_date": "2022-01-01",
                "modern_answer_hint": CONVERTIBLES_NOTE,
                "asc_pdf_path": "data/GAAP Data/Liabilities/470 Debt.pdf",
            }
    if chapter == 19:
        if _topic_matches(topic, CONVERTIBLES_CH19_TOPIC_KEYWORDS) or \
                _prompt_matches(prompt, CONVERTIBLES_PROMPT_KEYWORDS):
            return {
                "drift_topic_id": "convertibles",
                "asc_anchor": {"topic": 260, "subtopic": 10, "section": 45},
                "asu_number": "2020-06",
                "effective_date": "2022-01-01",
                "modern_answer_hint": CONVERTIBLES_NOTE,
                "asc_pdf_path": "data/GAAP Data/Presentation/260 earnings per share.pdf",
            }

    # 3. Goodwill two-step — Ch. 11
    if chapter == 11:
        topic_hit = _topic_matches(topic, GOODWILL_CH11_TOPIC_KEYWORDS)
        lo_hit = lo_code in GOODWILL_CH11_LOS if lo_code else False
        prompt_hit = _prompt_matches(prompt, GOODWILL_PROMPT_KEYWORDS)
        if topic_hit or lo_hit or prompt_hit:
            return {
                "drift_topic_id": "goodwill",
                "asc_anchor": {"topic": 350, "subtopic": 20, "section": 35},
                "asu_number": "2017-04",
                "effective_date": "2020-01-01",
                "modern_answer_hint": GOODWILL_NOTE,
                "asc_pdf_path": "data/GAAP Data/Assets/350 Intangibles-goodwill and other.pdf",
            }

    # 4. Income tax intraperiod + disclosure — Ch. 16
    if chapter == 16:
        topic_hit = _topic_matches(topic, TAX_CH16_TOPIC_KEYWORDS)
        lo_hit = lo_code in TAX_CH16_LOS if lo_code else False
        if topic_hit or lo_hit:
            return {
                "drift_topic_id": "tax",
                "asc_anchor": {"topic": 740, "subtopic": 20, "section": 45},
                "asu_number": "2019-12",
                "effective_date": "2020-01-01",
                "modern_answer_hint": TAX_NOTE,
                "asc_pdf_path": "data/GAAP Data/Expenses/740 Income taxes.pdf",
            }

    return None


# ============================================================================
# v1.1.0 — Standards-version smell triggers (plan §3, 12 patterns)
# ============================================================================
# Pre-compute case-insensitive regex hits over gold_answer + explanation +
# tables[].markdown + prompt. Each hit emits a dict with the trigger label
# and the matched span. Vera's mechanical_checks.py consumes this field at
# eval time.

# Each pattern is (label, regex, neg_lookbehind?). neg is a "must NOT also
# match" pattern used for the operating-lease and LIBOR triggers.
SMELL_PATTERNS = [
    ("risks_and_rewards", re.compile(r"risks?\s+and\s+rewards", re.IGNORECASE), None),
    (
        "operating_lease_no_rou",
        re.compile(r"operating\s+lease", re.IGNORECASE),
        re.compile(r"right[-\s]of[-\s]use|\bROU\b", re.IGNORECASE),
    ),
    ("extraordinary_item", re.compile(r"extraordinary\s+items?", re.IGNORECASE), None),
    (
        "incurred_loss",
        re.compile(
            r"incurred\s+loss|loss\s+has\s+been\s+incurred|probable\s+and\s+estimable",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        "goodwill_two_step",
        re.compile(
            r"two[-\s]step|Step\s*2|implied\s+fair\s+value\s+of\s+goodwill",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        "beneficial_conversion",
        re.compile(
            r"beneficial\s+conversion|\bBCF\b|cash\s+conversion\s+feature",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        "libor_no_sofr",
        re.compile(r"\bLIBOR\b", re.IGNORECASE),
        re.compile(r"\bSOFR\b|reference\s+rate\s+reform", re.IGNORECASE),
    ),
    (
        "afs_equity",
        re.compile(r"available[-\s]for[-\s]sale\s+equity|\bAFS\s+equity\b", re.IGNORECASE),
        None,
    ),
    (
        "cost_method_equity",
        re.compile(r"cost\s+method", re.IGNORECASE),
        None,
    ),
    (
        "pooling_of_interests",
        re.compile(r"pooling\s+of\s+interests", re.IGNORECASE),
        None,
    ),
    (
        "completed_contract_default",
        re.compile(r"completed[-\s]contract\s+method", re.IGNORECASE),
        None,
    ),
    (
        "direct_write_off",
        re.compile(r"direct\s+write[-\s]off\s+method", re.IGNORECASE),
        None,
    ),
]


def compute_smell_triggers(rec: dict) -> list[dict]:
    """Run the 12 patterns over the record's text fields. Return a stable
    sorted list of {label, span, source_field} for each hit."""
    fields: list[tuple[str, str]] = []
    if rec.get("prompt"):
        fields.append(("prompt", rec["prompt"]))
    if rec.get("gold_answer"):
        fields.append(("gold_answer", rec["gold_answer"]))
    if rec.get("explanation"):
        fields.append(("explanation", rec["explanation"]))
    for i, t in enumerate(rec.get("tables") or []):
        md = t.get("markdown") or ""
        if md:
            fields.append((f"tables[{i}].markdown", md))

    hits: list[dict] = []
    for label, pat, neg in SMELL_PATTERNS:
        for source, text in fields:
            for m in pat.finditer(text):
                if neg and neg.search(text):
                    continue
                span = m.group(0)
                hits.append({
                    "label": label,
                    "span": span,
                    "source_field": source,
                })
                # First hit per (label, source) is enough — avoid spamming
                # the same trigger 10x across a long rationale.
                break
    # Deterministic ordering for byte-stable JSONL.
    hits.sort(key=lambda h: (h["label"], h["source_field"], h["span"]))
    # Dedupe identical entries.
    seen: set = set()
    out: list[dict] = []
    for h in hits:
        k = (h["label"], h["source_field"], h["span"])
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out


# ============================================================================
# v1.1.0 — Hand-curated overrides (Carla + Pat, 2026-05-20)
# ============================================================================

CH12_Q199_GOLD = (
    "(1) DR Insurance expense 81,000 / "
    "DR Cash surrender value of life insurance 14,000 / "
    "CR Cash 95,000.\n"
    "(2) DR Cash 6,000,000 / "
    "CR Cash surrender value of life insurance 70,000 / "
    "CR Gain on life insurance settlement 5,930,000."
)

OVERRIDES = {
    # (chapter, question_number, source_row) -> dict of fields to overwrite
    (12, 199, 200): {
        "gold_answer": CH12_Q199_GOLD,
        "meta_update": {
            "gold_status": "ok",
            "exclude_from_scoring": False,
        },
        "warning": "recovered_from_table_per_carla_2026-05-20",
    },
    (21, 141, 143): {
        # Leave gold_answer null (already null); mark publisher_ambiguous.
        "meta_update": {
            "gold_status": "publisher_ambiguous",
            "exclude_from_scoring": True,
            "gold_unknown_reason": "ambiguous_legend_duplicate_not_reported_entries_1_and_5",
        },
        "warning": "publisher_ambiguous_per_pat_2026-05-20",
    },
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
        aacsb_raw = (cell(idx_aacsb) or "").strip() if cell(idx_aacsb) else None
        aacsb = canonicalize_aacsb(aacsb_raw)
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

        # v1.1.0 — meta block
        meta = {
            "gaap_divergence": False,
            "asc_anchor": None,
            "gaap_supersession": None,
            "standards_smell": [],
            "gold_status": "ok",
            "exclude_from_scoring": False,
        }

        # Carla's drift catalog (§2)
        drift = detect_drift(chapter_int, lo_code, topic, prompt_clean)
        if drift:
            meta["gaap_divergence"] = True
            meta["asc_anchor"] = drift["asc_anchor"]
            meta["gaap_supersession"] = {
                "asu_number": drift["asu_number"],
                "effective_date": drift["effective_date"],
                "modern_answer_hint": drift["modern_answer_hint"],
                "asc_pdf_path": drift["asc_pdf_path"],
            }
            stats["drift_total"] += 1
            stats[f"drift_{drift['drift_topic_id']}"] += 1

        # Smell triggers (§3) — run against the in-progress record
        smell_hits = compute_smell_triggers(rec)
        if smell_hits:
            meta["standards_smell"] = smell_hits
            stats["smell_records_hit"] += 1
            stats["smell_hits_total"] += len(smell_hits)
            for h in smell_hits:
                stats[f"smell_{h['label']}"] += 1
            # Ch.15 in Spiceland 9e teaches ASC 842 (PROVENANCE confirms).
            # "operating lease" mentions in Ch.15 are current-GAAP-correct;
            # flag for Carla review rather than treating as legacy drift.
            if chapter_int == 15 and any(
                h["label"] == "operating_lease_no_rou" for h in smell_hits
            ):
                meta["smell_review_needed"] = True
                stats["smell_review_needed_ch15_lease"] += 1
            # Ch.12 "cost method" hits — Spiceland Ch.12 teaches the equity
            # method post-ASU 2016-01 (FV through NI for most non-significant
            # equity holdings). The "cost method" reference may be a vestigial
            # textbook phrase; flag for Carla.
            if chapter_int == 12 and any(
                h["label"] == "cost_method_equity" for h in smell_hits
            ):
                meta["smell_review_needed"] = True
                stats["smell_review_needed_ch12_cost_method"] += 1

        # Hand-curated overrides (§5) — apply by (chapter, qnum, source_row)
        ov_key = (chapter_int, qnum, excel_row_idx)
        if ov_key in OVERRIDES:
            ov = OVERRIDES[ov_key]
            if "gold_answer" in ov:
                rec["gold_answer"] = ov["gold_answer"]
                stats["override_gold_filled"] += 1
            for k, v in ov.get("meta_update", {}).items():
                meta[k] = v
            stats[f"override_applied:{ov_key[0]}_q{ov_key[1]}"] += 1
            warnings_out.append(
                f"ch{chapter} row{excel_row_idx}: override applied — {ov['warning']}"
            )

        # Empty-gold gold_status fallback (only fires if no override above
        # set gold_status to something explicit).
        if not rec.get("gold_answer") and meta["gold_status"] == "ok":
            meta["gold_status"] = "table_only" if rec["tables"] else "publisher_ambiguous"

        rec["meta"] = meta
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

    # Write warnings with v1.1.0 changelog block at the top
    changelog_lines = [
        "_v1_1_0_changelog:",
        "  date: 2026-05-20",
        "  schema_version: " + SCHEMA_VERSION,
        "  jsonl_sha256: " + jsonl_sha,
        "  changes:",
        "    - schema: added meta block (gaap_divergence, asc_anchor,",
        "      gaap_supersession, standards_smell, gold_status,",
        "      exclude_from_scoring) per plan §1",
        "    - aacsb: canonicalized 51 raw variants -> "
        + str(len({tok for r in all_records for tok in (r.get('aacsb') or [])}))
        + " canonical labels, emitted as list[str] per plan §4",
        "    - ch12_q0199 (source_row 200): recovered_from_table_per_carla_2026-05-20",
        "      gold_answer populated from table per Carla CPA review",
        "    - ch21_q0141 (source_row 143): publisher_ambiguous_per_pat_2026-05-20",
        "      gold_answer remains null; meta.gold_status='publisher_ambiguous';",
        "      meta.exclude_from_scoring=true; gold_unknown_reason set",
        "    - drift catalog: " + str(sum(1 for r in all_records if (r.get('meta') or {}).get('gaap_divergence')))
        + " records flagged meta.gaap_divergence=true",
        "      (CECL Ch7/Ch12, convertibles Ch14/Ch19, goodwill Ch11, tax Ch16)",
        "    - smell triggers: 12 case-insensitive patterns pre-computed; "
        + str(sum(len((r.get('meta') or {}).get('standards_smell') or []) for r in all_records))
        + " hits across " + str(sum(1 for r in all_records if (r.get('meta') or {}).get('standards_smell')))
        + " records",
        "  v1_0_0_retired: 95f1ae448c693088b893758ffd24f667aed08593bc107611c9af722ff8f54e4b",
        "  v1_1_0_anchor: " + jsonl_sha,
        "",
    ]
    body = "\n".join(warnings) + "\n" if warnings else ""
    WARNINGS_LOG.write_text("\n".join(changelog_lines) + body, encoding="utf-8")
    print(f"wrote {WARNINGS_LOG}  ({len(warnings):,} warnings)")

    # Per-Bloom / per-Difficulty / per-Question_Type rollups
    by_chapter = Counter()
    by_bloom_primary = Counter()
    by_difficulty = Counter()
    by_type = Counter()
    aacsb_all = Counter()
    by_gold_status = Counter()
    by_drift_topic = Counter()
    excluded_from_scoring = 0
    for r in all_records:
        by_chapter[r["chapter"]] += 1
        if r.get("bloom"):
            by_bloom_primary[r["bloom"][0]] += 1
        else:
            by_bloom_primary["(none)"] += 1
        by_difficulty[r.get("difficulty") or "(none)"] += 1
        by_type[r.get("type") or "(none)"] += 1
        for tag in r.get("aacsb") or []:
            aacsb_all[tag] += 1
        meta = r.get("meta") or {}
        by_gold_status[meta.get("gold_status", "ok")] += 1
        if meta.get("exclude_from_scoring"):
            excluded_from_scoring += 1
        if meta.get("gaap_divergence"):
            gs = meta.get("gaap_supersession") or {}
            asu = gs.get("asu_number")
            by_drift_topic[asu or "(unknown)"] += 1

    # Write stats — use a fixed filename for v1.1.0 anchor, plus a timestamped
    # archive copy for the run log.
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stats_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_in": len(all_records) + all_stats.get("header_artifact_dropped", 0)
                    + all_stats.get("row_skipped_no_qnum", 0),
        "total_records": len(all_records),
        "rows_kept": len(all_records),
        "rows_dropped": all_stats.get("header_artifact_dropped", 0)
                        + all_stats.get("row_skipped_no_qnum", 0),
        "jsonl_sha256": jsonl_sha,
        "jsonl_bytes": len(jsonl_bytes),
        "aacsb_canonical_unique_count": len(aacsb_all),
        "aacsb_canonical_values": dict(aacsb_all),
        "by_chapter": {str(k): v for k, v in sorted(by_chapter.items())},
        "by_bloom_primary": dict(by_bloom_primary),
        "by_difficulty": dict(by_difficulty),
        "by_question_type": dict(by_type),
        "by_gold_status": dict(by_gold_status),
        "by_drift_asu": dict(by_drift_topic),
        "exclude_from_scoring_count": excluded_from_scoring,
        "totals": dict(all_stats),
        "per_chapter_stats": per_chapter,
    }
    stats_path = STATS_DIR / f"run_{ts}.json"
    stats_path.write_text(
        json.dumps(stats_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {stats_path}")

    # Also write the named v1.1.0 anchor.
    anchor_path = STATS_DIR / "run_v1.1.0.json"
    anchor_path.write_text(
        json.dumps(stats_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {anchor_path}")

    print("\n=== TOTALS ===")
    for k, v in sorted(all_stats.items(), key=lambda x: -x[1]):
        print(f"  {k:40s} {v:,}")


if __name__ == "__main__":
    main()
