"""
eval/mechanical_checks.py
Vera's 4 structural checks + 12 standards-smell aggregation.
Called by eval/run.py after all predictions are produced.

Inputs
------
predictions : list[dict]  — each dict is a row from test_predictions.jsonl
canonical   : dict[id -> canonical_record]  — eval/spiceland9e.jsonl keyed by meta.id
                (used for pre-computed meta.standards_smell)

Returns
-------
dict — the `mechanical_checks` block that goes into test_metrics.json
"""

import re
from typing import Any

# ── Bloom taxonomy ──────────────────────────────────────────────────────────
# Check 4: reasoning-pattern expected to match Bloom level.
# r0 doesn't emit an explicit reasoning_pattern field; we infer from generation
# length and presence of step markers as a proxy:
#   Remember/Understand → short answer (≤ 30 tokens) → "CoT-short" (passes)
#   Apply/Analyze/Evaluate/Create → may need multi-step → flag if single-token
BLOOM_LOWER_GROUPS = {"remember", "understand"}
BLOOM_UPPER_GROUPS = {"apply", "analyze", "evaluate", "create"}

# ── Standards-smell regex patterns (§3 of v1_1_0_plan.md) ──────────────────
SMELL_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("risks_and_rewards",
     "pre-ASC-606 revenue legacy",
     re.compile(r"risks?\s+and\s+rewards?", re.IGNORECASE)),
    ("operating_lease_no_rou",
     "pre-ASC-842 lease legacy",
     re.compile(r"operating\s+lease(?!.*right.of.use)(?!.*ROU)", re.IGNORECASE | re.DOTALL)),
    ("extraordinary_items",
     "pre-ASU 2015-01 income-statement legacy",
     re.compile(r"extraordinary\s+items?", re.IGNORECASE)),
    ("incurred_loss",
     "pre-CECL (ASU 2016-13) ASC 326 drift",
     re.compile(
         r"incurred\s+loss|loss\s+has\s+been\s+incurred|probable\s+and\s+estimable",
         re.IGNORECASE,
     )),
    ("goodwill_two_step",
     "pre-ASU 2017-04 goodwill drift",
     re.compile(r"two.step|Step\s+2\b|implied\s+fair\s+value\s+of\s+goodwill", re.IGNORECASE)),
    ("beneficial_conversion",
     "pre-ASU 2020-06 convertibles drift",
     re.compile(r"beneficial\s+conversion|BCF\b|cash\s+conversion\s+feature", re.IGNORECASE)),
    ("libor_no_sofr",
     "pre-ASU 2020-04/2022-06 rate-reform stale",
     re.compile(r"LIBOR(?!.*SOFR)(?!.*reference\s+rate\s+reform)", re.IGNORECASE | re.DOTALL)),
    ("afs_equity",
     "pre-ASU 2016-01 equity-investment legacy",
     re.compile(r"available.for.sale\s+equity|AFS\s+equity", re.IGNORECASE)),
    ("cost_method_equity",
     "pre-ASU 2016-01 equity-investment legacy",
     re.compile(r"cost\s+method", re.IGNORECASE)),
    ("pooling_of_interests",
     "pre-SFAS 141 (2001) sanity check",
     re.compile(r"pooling\s+of\s+interests", re.IGNORECASE)),
    ("completed_contract",
     "pre-ASC-606 revenue legacy",
     re.compile(r"completed.contract\s+method", re.IGNORECASE)),
    ("direct_writeoff_gaap",
     "always-wrong hard FAIL",
     re.compile(r"direct\s+write.off\s+method", re.IGNORECASE)),
]


def _extract_decimal_numbers(text: str) -> set[str]:
    """Return all decimal-number tokens found in text (digits with optional decimal point)."""
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", text))


def _generation_token_count_approx(generation: str) -> int:
    """Rough whitespace-based token count for the generation string."""
    return len(generation.split())


def run_checks(
    predictions: list[dict[str, Any]],
    canonical: dict[str, Any],
    solver_emits_citations: bool = False,
    solver_emits_tool_calls: bool = False,
) -> dict[str, Any]:
    """
    Run all 4 mechanical checks + smell aggregation on the prediction list.

    Each prediction dict must have at minimum:
        question_id, type, primary_bloom, generation,
        (optional) tool_calls, citations

    Capability flags (Vera audit 2026-05-21): checks 2 + 3 only fire when the
    corresponding solver capability is wired. Without these, r0-class runs that
    emit `citations=[]` and `tool_calls=[]` trigger blanket violations that
    make `gate_pass` permanently False regardless of model accuracy. The flags
    default False; the solver-loop owner flips them on once Solomon's
    citation/tool layer is in place.
    """
    results: dict[str, Any] = {
        # Capability flags echoed back so the verdict is interpretable
        "capability_flags": {
            "solver_emits_citations":  solver_emits_citations,
            "solver_emits_tool_calls": solver_emits_tool_calls,
        },
        # Check 1 – JE balance (only applicable when tool_calls has journal_entry_validator)
        "je_balance_violations": 0,
        "je_balance_violation_ids": [],
        # Check 2 – citation present at Bloom Remember/Understand
        "missing_citation_violations": 0,
        "missing_citation_violation_ids": [],
        "missing_citation_check_status": (
            "active" if solver_emits_citations
            else "n/a (solver_emits_citations=False)"
        ),
        # Check 3 – arithmetic in prose at Apply+
        "arith_in_prose_violations": 0,
        "arith_in_prose_violation_ids": [],
        "arith_in_prose_check_status": (
            "active" if solver_emits_tool_calls
            else "n/a (solver_emits_tool_calls=False)"
        ),
        # Check 4 – reasoning pattern matches Bloom (single-token at Apply+ flagged)
        "reasoning_pattern_drift": 0,
        "reasoning_pattern_drift_ids": [],
        # Standards-smell aggregation
        "smell_flags_total": 0,
        "smell_introduced_by_model": 0,   # gold had no smell; model generation introduces it
        "smell_by_label": {},
        "smell_introduced_ids": [],
    }

    for pred in predictions:
        qid = pred.get("question_id", "?")
        bloom = (pred.get("primary_bloom") or "").strip()
        generation = pred.get("generation") or ""
        tool_calls = pred.get("tool_calls") or []
        citations = pred.get("citations") or []
        bloom_lower = bloom.lower()

        # ── Check 1: JE balance ─────────────────────────────────────────────
        for tc in tool_calls:
            if isinstance(tc, dict) and tc.get("name") == "journal_entry_validator":
                result = tc.get("result", {})
                if isinstance(result, dict) and result.get("balanced") is False:
                    results["je_balance_violations"] += 1
                    results["je_balance_violation_ids"].append(qid)
                    break

        # ── Check 2: citation at Remember/Understand ────────────────────────
        # Only fires when the solver is configured to emit citations.
        if solver_emits_citations and bloom_lower in BLOOM_LOWER_GROUPS:
            if not citations:
                results["missing_citation_violations"] += 1
                results["missing_citation_violation_ids"].append(qid)

        # ── Check 3: arithmetic in prose at Apply+ ──────────────────────────
        # Only fires when the solver is configured to emit tool_calls.
        if solver_emits_tool_calls and bloom_lower in BLOOM_UPPER_GROUPS:
            tool_result_numbers: set[str] = set()
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tool_result_text = str(tc.get("result", ""))
                    tool_result_numbers |= _extract_decimal_numbers(tool_result_text)
            prose_numbers = _extract_decimal_numbers(generation)
            unsourced = prose_numbers - tool_result_numbers
            if unsourced:
                results["arith_in_prose_violations"] += 1
                results["arith_in_prose_violation_ids"].append(qid)

        # ── Check 4: reasoning pattern / Bloom mapping ──────────────────────
        # r0 doesn't emit an explicit reasoning_pattern; proxy: at Apply+,
        # if the model produces a near-single-token answer (≤ 3 words) flag it
        # as reasoning-pattern drift (expected multi-step ReAct or CoT, got none).
        if bloom_lower in BLOOM_UPPER_GROUPS:
            approx_tokens = _generation_token_count_approx(generation)
            qtype = (pred.get("type") or "").strip()
            # Essay/Problem at Apply+ with ≤ 5 words is a clear drift
            if qtype == "Essay/Problem" and approx_tokens <= 5:
                results["reasoning_pattern_drift"] += 1
                results["reasoning_pattern_drift_ids"].append(qid)

        # ── Standards-smell check ────────────────────────────────────────────
        # Pre-computed smells from canonical meta (on the gold text).
        can_rec = canonical.get(qid) or {}
        gold_smells_labels = {
            s.get("label", "") if isinstance(s, dict) else str(s)
            for s in (can_rec.get("meta") or {}).get("standards_smell", [])
        }

        # Check model generation for smell triggers
        generation_smell_labels: set[str] = set()
        for label, _desc, pattern in SMELL_PATTERNS:
            if pattern.search(generation):
                generation_smell_labels.add(label)

        # Aggregate total smell flags (generation hits)
        if generation_smell_labels:
            results["smell_flags_total"] += len(generation_smell_labels)
            for lbl in generation_smell_labels:
                results["smell_by_label"][lbl] = results["smell_by_label"].get(lbl, 0) + 1

        # Smell *introduced* by model: model generates a trigger the gold did NOT have
        introduced = generation_smell_labels - gold_smells_labels
        if introduced:
            results["smell_introduced_by_model"] += len(introduced)
            results["smell_introduced_ids"].append(
                {"id": qid, "introduced": sorted(introduced)}
            )

    # Mechanical gate summary. N/A checks do not block (their violation counts
    # stay 0 by construction, but we record the status separately so a reader
    # can tell PASS-because-active from PASS-because-skipped).
    results["gate_pass"] = (
        results["je_balance_violations"] == 0
        and results["missing_citation_violations"] == 0
        and results["arith_in_prose_violations"] == 0
        and results["reasoning_pattern_drift"] == 0
    )
    results["gate_active_checks"] = [
        name for name, active in [
            ("je_balance",         True),    # always active (no-op when tool_calls=[])
            ("missing_citation",   solver_emits_citations),
            ("arith_in_prose",     solver_emits_tool_calls),
            ("reasoning_pattern",  True),
        ]
        if active
    ]
    # Smell gate is advisory (non-blocking for r0; Carla adjudicates)
    results["smell_gate_pass"] = results["smell_introduced_by_model"] == 0

    return results
