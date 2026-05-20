"""Shared rendering helpers for SFT chat-template formatting.

Produces `{"messages": [system, user, assistant], "meta": {...}}` records
from canonical `eval/spiceland9e.jsonl` rows. Used by the multi-seed
splitter (`split_multi_seed.py`). Format is model-agnostic — apply the
per-model chat template at training time with
`tokenizer.apply_chat_template()`.
"""
from __future__ import annotations

import hashlib
import re

SYSTEM_PROMPT = (
    "You are a graduate-level intermediate financial accounting tutor with deep "
    "knowledge of US GAAP (FASB ASC) and the Spiceland 9e curriculum. When you "
    "answer, cite the controlling chapter and learning objective if given, show "
    "your reasoning step by step for computational problems, and present journal "
    "entries in standard debit-on-top format. Use exact-decimal arithmetic for "
    "money amounts; do not round prematurely. If a problem provides tables, "
    "preserve and reference them in your reasoning."
)

# Scenario preambles that the publisher uses to introduce shared scenarios.
# Stripping these prevents two siblings of the same scenario from being
# distinguished by minor preamble differences when fingerprinting.
_PREAMBLE_PATTERNS = [
    re.compile(r"^Use this information to answer the following questions?[:.\s]*",
               re.IGNORECASE),
    re.compile(r"^Refer to the following information[:.\s]*", re.IGNORECASE),
    re.compile(r"^Use the following to answer the questions?\s*below[:.\s]*",
               re.IGNORECASE),
    re.compile(r"^Use the following information[:.\s]*", re.IGNORECASE),
    re.compile(r"^The following information.*?(applies to|relates to|is for)\b[:.\s]*",
               re.IGNORECASE | re.DOTALL),
]


def scenario_fingerprint(prompt: str) -> str:
    """Return a stable 16-hex-char fingerprint identifying a question scenario.

    Two questions sharing the same first ~300 chars of normalized prompt
    (after stripping the 'N) ' question marker and the common 'Use this
    information' preamble) hash to the same fingerprint and therefore land
    in the same split. Conservative on length to keep adjacent sub-questions
    that legitimately repeat scenario data together (e.g. ch05 Cupid
    Construction sub-questions 185-188 all share a scenario).
    """
    s = re.sub(r"^\s*\d+\)\s*", "", prompt or "")
    for pat in _PREAMBLE_PATTERNS:
        s = pat.sub("", s, count=1)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return hashlib.sha1(s[:300].encode("utf-8")).hexdigest()[:16]


def is_worked_solution(assistant_msg: str) -> bool:
    """A worked-solution assistant message has either substantial length OR
    a newline (indicating structured multi-step content). Single-letter MC
    answers (`**C**`) and single-token Matching answers (`1`) return False."""
    a = (assistant_msg or "").strip()
    if len(a) <= 5:
        return False
    if "\n" in a:
        return True
    return len(a) > 200


def render_lo_header(rec: dict) -> str:
    lo = rec.get("lo") or {}
    parts = [f"Chapter {rec['chapter']}"]
    if lo.get("code"):
        parts.append(f"LO {lo['code']}")
    if rec.get("topic"):
        parts.append(rec["topic"])
    head = "[" + " · ".join(parts) + "]"
    if lo.get("text"):
        head += f"\nLearning objective: {lo['text']}"
    return head


def render_user_message(rec: dict) -> str:
    parts = [render_lo_header(rec), "", rec["prompt"]]
    if rec.get("options"):
        parts.append("")
        parts.append("Options:")
        for opt in rec["options"]:
            parts.append(opt)
    tables = rec.get("tables") or []
    if tables:
        parts.append("")
        parts.append("Relevant tables:")
        for t in tables:
            parts.append("")
            ctx_before = (t.get("context_before") or "").strip()
            if ctx_before and not ctx_before.endswith((".", ":", "?", ")")):
                ctx_before += ":"
            if ctx_before:
                parts.append(ctx_before)
            parts.append(t.get("markdown", ""))
    return "\n".join(parts).strip()


def render_assistant_message(rec: dict) -> str:
    qtype = rec.get("type") or ""
    gold = (rec.get("gold_answer") or "").strip()
    expl = (rec.get("explanation") or "").strip()
    if qtype in ("Multiple Choice", "True/False"):
        if qtype == "Multiple Choice" and len(gold) == 1 and gold.isalpha():
            head = f"**{gold}**"
        elif qtype == "True/False":
            head = f"**{gold.upper()}**" if gold else gold
        else:
            head = gold
        return f"{head}\n\n{expl}".strip() if expl else head
    # Essay/Problem/Matching: gold is the worked answer; explanation is rare
    if expl and gold:
        return f"{gold}\n\n{expl}".strip()
    return (gold or expl or "").strip()


def build_messages(rec: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_user_message(rec)},
        {"role": "assistant", "content": render_assistant_message(rec)},
    ]


def should_skip(rec: dict) -> str | None:
    """Skip rules. Return reason or None."""
    if not rec.get("gold_answer"):
        return "no_gold_answer"
    if not (rec.get("prompt") or "").strip():
        return "no_prompt"
    return None
