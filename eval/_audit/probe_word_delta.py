"""Investigate why Excel has +713 more 'real questions' than Word has Answer-lines.

Hypothesis 1: Word Answer: regex is too strict (whitespace variations).
Hypothesis 2: Word stores some answers inside table cells, not paragraphs.
Hypothesis 3: The Excel was sourced partly from Word and partly from another
              source (e.g. Connect online platform).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from docx import Document

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORD_DIR = Path(r"D:\Github\accounting\data\Intermediate Financial Accounting test bank\word")


def find_one(chapter: str) -> Path:
    matches = [p for p in WORD_DIR.iterdir()
               if p.suffix == ".docx" and not p.name.startswith("~$")
               and f"Chapter{chapter}" in p.name]
    return matches[0]


# Regexes — strict vs lenient
RE_STRICT = re.compile(r"^\s*Answer:\s", re.IGNORECASE)        # original
RE_LENIENT = re.compile(r"^\s*Answer\s*[:\s]", re.IGNORECASE)  # whitespace-tolerant
RE_VERY_LENIENT = re.compile(r"\bAnswer\b\s*[:\.\s]", re.IGNORECASE)  # anywhere

RE_Q_MARKER = re.compile(r"^\s*(\d+)\)\s")


def main() -> None:
    print(f"{'Ch':>3} | {'paras':>6} | {'q_starts':>8} | {'strict':>6} | {'lenient':>7} | {'very':>5} | {'in_tables':>9} | {'qmax':>5}")
    print("-" * 90)
    grand_strict = 0
    grand_lenient = 0
    grand_very = 0
    grand_in_tables = 0
    grand_qmax = 0
    for i in range(1, 22):
        ch = f"{i:02d}"
        doc = Document(str(find_one(ch)))
        # Paragraph-level
        paras = [p.text for p in doc.paragraphs]
        nonempty = [p for p in paras if p.strip()]
        strict = sum(1 for p in nonempty if RE_STRICT.match(p))
        lenient = sum(1 for p in nonempty if RE_LENIENT.match(p))
        # very-lenient: match anywhere in any paragraph (could over-count)
        very = sum(1 for p in nonempty if RE_VERY_LENIENT.search(p))
        q_starts = sum(1 for p in nonempty if RE_Q_MARKER.match(p))
        qmax = 0
        for p in nonempty:
            m = RE_Q_MARKER.match(p)
            if m:
                qmax = max(qmax, int(m.group(1)))
        # Table-level: any cell whose text contains "Answer:"
        in_tables = 0
        for t in doc.tables:
            for r in t.rows:
                for c in r.cells:
                    if RE_STRICT.match(c.text.strip()) or RE_LENIENT.match(c.text.strip()):
                        in_tables += 1
        grand_strict += strict
        grand_lenient += lenient
        grand_very += very
        grand_in_tables += in_tables
        grand_qmax += qmax
        print(f"{ch:>3} | {len(paras):>6} | {q_starts:>8} | {strict:>6} | {lenient:>7} | {very:>5} | {in_tables:>9} | {qmax:>5}")
    print("-" * 90)
    print(f"TOT |        |          | {grand_strict:>6} | {grand_lenient:>7} | {grand_very:>5} | {grand_in_tables:>9} | {grand_qmax:>5}")


if __name__ == "__main__":
    main()
