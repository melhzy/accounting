"""Probe Word docs to see what content sits between 'Answer:' and the next
question marker for MC / TF / Matching / Essay questions. The hypothesis is
that Word may carry worked-solution rationale that the Excel Explanation
column doesn't have (especially for Ch.01-05 which lack Explanation entirely)."""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORD_DIR = Path(r"D:\Github\accounting\data\Intermediate Financial Accounting test bank\word")
Q_MARKER = re.compile(r"^\s*(\d+)\)(\s|$)")
ANSWER_PARA = re.compile(r"^\s*Answer:\s*(.+)?$", re.IGNORECASE)
META_PARA = re.compile(
    r"^\s*(Difficulty|Topic|Learning Objective|Bloom['’]?s|AACSB|AICPA|Accessible/AICPA|Question Type)\s*:",
    re.IGNORECASE,
)


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


def find_word(chapter: str) -> Path:
    matches = [p for p in WORD_DIR.iterdir()
               if p.suffix == ".docx" and not p.name.startswith("~$")
               and f"Chapter{chapter}" in p.name]
    return matches[0]


def probe_chapter(chapter: str) -> dict:
    path = find_word(chapter)
    doc = Document(str(path))

    # Walk body in order, gather paragraph + table runs by question, separating
    # what's between "Answer:" and the next metadata line / next question / end.
    current_q: int | None = None
    after_answer: bool = False
    answer_text: str | None = None
    # per-question rationale = list of paragraph texts (and "[TABLE]" tokens for tables)
    rationale_by_q: dict[int, list[str]] = defaultdict(list)
    answer_by_q: dict[int, str] = {}

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            m_q = Q_MARKER.match(text)
            if m_q:
                n = int(m_q.group(1))
                if current_q is None or n > current_q:
                    current_q = n
                    after_answer = False
                    answer_text = None
                    continue
                # In-question enumeration — keep accumulating if after_answer
            if current_q is None:
                continue
            m_ans = ANSWER_PARA.match(text)
            if m_ans:
                after_answer = True
                answer_text = (m_ans.group(1) or "").strip()
                answer_by_q[current_q] = answer_text
                continue
            if after_answer:
                # Stop accumulating once we hit a metadata line
                if META_PARA.match(text):
                    after_answer = False
                    continue
                rationale_by_q[current_q].append(text)
        elif isinstance(block, Table):
            if current_q is not None and after_answer:
                # Capture a flattened table summary
                cells = []
                for r in block.rows:
                    for c in r.cells:
                        t = c.text.strip()
                        if t and t not in cells:
                            cells.append(t)
                preview = " | ".join(cells[:8])
                rationale_by_q[current_q].append(f"[TABLE {len(block.rows)}r×{len(block.rows[0].cells) if block.rows else 0}c: {preview[:120]}]")

    # Aggregate
    stats = {
        "chapter": chapter,
        "n_questions_seen": len(answer_by_q),
        "n_with_rationale_paragraphs": sum(1 for v in rationale_by_q.values() if any(not s.startswith("[TABLE") for s in v)),
        "n_with_rationale_tables_only": sum(1 for v in rationale_by_q.values() if v and all(s.startswith("[TABLE") for s in v)),
        "n_with_any_post_answer_content": len(rationale_by_q),
        "rationale_length_distribution": [],
    }
    lengths = [sum(len(s) for s in v) for v in rationale_by_q.values()]
    lengths.sort()
    if lengths:
        stats["rationale_length_distribution"] = {
            "p50": lengths[len(lengths) // 2],
            "p95": lengths[int(len(lengths) * 0.95)] if len(lengths) > 20 else lengths[-1],
            "max": lengths[-1],
            "n": len(lengths),
        }
    # Capture a sample of 3 rationale-bearing questions for inspection
    samples = []
    for q, paras in rationale_by_q.items():
        if any(not s.startswith("[TABLE") for s in paras) and len(samples) < 3:
            sample_text = "\n".join(paras)[:400]
            samples.append({"q": q, "answer": answer_by_q.get(q, ""), "rationale_preview": sample_text})
    stats["samples"] = samples
    return stats


def main() -> None:
    print(f"{'Ch':>3} | {'#q':>4} | {'rat_para':>8} | {'rat_tbl_only':>12} | {'any':>4} | p50 | p95 | max")
    print("-" * 70)
    for i in range(1, 22):
        ch = f"{i:02d}"
        s = probe_chapter(ch)
        dist = s["rationale_length_distribution"] or {}
        print(f"{ch:>3} | {s['n_questions_seen']:>4} | {s['n_with_rationale_paragraphs']:>8} | "
              f"{s['n_with_rationale_tables_only']:>12} | {s['n_with_any_post_answer_content']:>4} | "
              f"{dist.get('p50', '-'):>3} | {dist.get('p95', '-'):>3} | {dist.get('max', '-'):>5}")
    print()
    print("=== Sample rationales from Ch.05 ===")
    s = probe_chapter("05")
    for samp in s["samples"]:
        print(f"\nQ#{samp['q']} (Answer={samp['answer']!r}):")
        print(samp["rationale_preview"])


if __name__ == "__main__":
    main()
