# `spiceland9e-v1.2.0` — queued implementation plan (worked-solution filter)

_Pat-arbiter v1.2.0 scope, ratified by user 2026-05-22 via lens fan-out (Diana + Carla + Edie + Leo's lens-doc applied + Pat synthesis). **Do not run yet** — explicitly sequenced AFTER r1 (Qwen3-8B size ablation) and r2 (DeepSeek-R1-distill reasoning prior) execute on the DGX Spark row, so we know whether the symptom is a 4B-capacity issue or a true data-coverage issue before paying to fix it._

## Trigger

The executed `qwen3-4b-4bit-qlora-s00-r0` adapter (69.2% on the 464-row scorable test split) collapsed to answer-only outputs (`**A**`, `**TRUE**`) while the baseline `unsloth/Qwen3-4B-Instruct-2507` produces explanations. Root cause:

- ~50% of `eval/sft/splits/seed_00__351199285/train.jsonl` assistant turns are ≤12 chars.
- Canonical `eval/spiceland9e.jsonl` explanation coverage by type: MC 50% · Essay 48% · **TF 0.2%** · **Matching 0.1%**.
- **Publisher convention, not an ETL gap.** Diana ran the regex catalog across all 21 chapters: only `Explanation:` ever appears in source. Excel `Explanation` column is 1/250 populated for TF, 0/532 for Matching across Ch.06-21. Word fallback is firing as designed; there is nothing to extract.

## Verdict (Pat-synthesized, 2026-05-22)

**Pick option A (filter), sequenced AFTER r1 + r2.** Rank: **A > B > D > C**.

| # | Option | Verdict |
|---|---|---|
| A | Filter SFT to `meta.has_worked_solution == True` | **chosen** — 5-line change in `eval/split_multi_seed.py`, ~2,070 rows survive, no fabrication, every example coaching-capable |
| B | Synthesize TF/Matching rationales with a teacher model | parked — entry-gated on r1/r2-with-A still under-explaining on Apply; carries Carla's discipline list (below) |
| C | Per-segment loss weighting (downweight short rows) | stays deferred — same status as r0 decision log (custom collator required) |
| D | Hand-author rationales for top-10 LOs | reserve — narrow top-up if a specific LO under-explains after A |

### Why this ranking (lens-by-lens)

- **Diana**: PASS on the source audit. No ETL fix possible — the rationale is genuinely absent at publisher source for TF and Matching. Recommendation: downstream fix only.
- **Carla**: Synthesized rationales are ACCEPTABLE WITH DISCIPLINE — defensible for TF (bright-line rule citations) and Matching (definitional contrast, not multi-step reasoning). Required disciplines listed below in §3.
- **Edie**: The user's "rationale for every type" is the right product goal but the **wrong training-data gate**. The right gate is **"every SFT example must produce a coaching-capable output."** Drop rationale-less TF/Matching from SFT; keep them in eval as graded-assessment surface only. Bloom × type rationale-shape table archived below in §4 for option B's prompt design if reached.
- **Leo** (applied from `leo-llm.md`): Sequence load-bearing. Four-axis selection (accuracy on Vera's Apply slice dominates → $/q → latency → privacy) says do NOT spend r3-class synthesis effort before r1+r2 close. r1 isolates parameter count (4B→8B); r2 isolates pretraining lineage (vanilla Qwen3 → R1-distill). If either one fixes the explanation collapse on its own, we don't need v1.2.0 at all. If both still under-explain on Apply, v1.2.0 lands.

### Named tradeoff

A drops ~30% of training rows (4,453 → ~2,070 eligible after the worked-solution filter and the existing skip rules) to recover coaching fidelity. Vera must confirm the smaller cleaner corpus does not regress MC-Remember or calculation slices by >1pp versus r0's 69.2%. If it does, B becomes the entry-gated next move.

## §1 — Acceptance criteria

The v1.2.0 corpus PASSES when:

- [ ] **r1 and r2 have executed** and both `test_metrics.json` deltas vs r0's 69.2% are on Vera's slice table. **This is the launch gate** — v1.2.0 work does not start before this.
- [ ] If r1-vs-r0 OR r2-vs-r0 shows a reasonable per-Bloom Apply-slice lift AND restoration of explanations on a Vera "rationale-present" qualitative probe → **v1.2.0 cancelled** (the larger model / reasoning prior solved it).
- [ ] If both r1 and r2 still produce answer-only outputs → **v1.2.0 launches**.
- [ ] `eval/split_multi_seed.py` filters records with `meta.has_worked_solution == False` from SFT splits (train + valid + test) BEFORE the scenario-grouping step.
- [ ] `eval/spiceland9e.jsonl` itself UNCHANGED — the filter happens at split time, not at canonical-JSONL time. TF/Matching rows stay in the canonical corpus for Vera's graded-assessment eval surface.
- [ ] New SFT split shas under `eval/sft/splits/seed_*/manifest.json`; top-level `manifest.json` records dataset version `spiceland9e-v1.2.0` with the filter rule in `noise_rules` block.
- [ ] `eval/README.md` documents the filter + the "TF/Matching in eval-only, not train" boundary.
- [ ] Vera adds a `by_rationale_presence` slice column to `test_metrics.json` so the v1.2.0 vs r0 A/B can be sliced by "did the question have a publisher rationale".
- [ ] r0/r1/r2 are re-run against v1.2.0 splits (3 fresh adapters with new `source_jsonl_sha256` bindings); Vera A/B vs the v1.1.0-bound r0 baseline drives PASS/FAIL.

## §2 — Versioning event

The filter is a **MAJOR** dataset-version bump per ROADMAP §1's noise-rule semantics rule: a record's SFT inclusion flips on `meta.has_worked_solution`. So `spiceland9e-v1.1.0` → `spiceland9e-v1.2.0`, new `source_jsonl_sha256`.

The pipeline version stays at `pipeline-v0.3.0` if the filter is purely a constant change in `split_multi_seed.py`; bumps to `pipeline-v0.4.0` if the filter changes the split contract (e.g. the worked-solution filter alters the scenario-grouping rule because some scenarios are split across worked + non-worked sub-questions). Diana decides at implementation time.

## §3 — Carla's discipline list (parked for option B)

Active only if v1.1.0-or-later r0/r1/r2 still under-explain after v1.2.0 lands. **Do not execute until Pat re-opens the gate.**

If synthesizing TF + Matching rationales becomes necessary:

1. **Teacher pin + provenance class field.** Record `teacher_model`, `teacher_sha`/version, `prompt_sha`, `generated_at` per row. Synthesized rationales are a separate provenance class from publisher rationales — never silently merge.
2. **Citation must regex-resolve.** Every ASC/IFRS paragraph the teacher emits gets validated against a known-good list of citable paragraphs in the Spiceland 9e LOs. Unresolvable citation → reject; no "best-effort keep".
3. **Standards-version gate.** Re-use Diana's v1.1.0 `meta.standards_smell` triggers as hard rejects on the synth stream: pre-606 ("risks and rewards", "earnings process complete"), pre-842 ("operating lease" without ROU language for lessee), direct-write-off-as-GAAP, LIFO on IFRS-tagged rows.
4. **Answer-consistency check.** Teacher rationale must conclude with the gold answer. If it argues the opposite, **reject — do not auto-fix**. The disagreement is signal that the question is ambiguous or gold is wrong; escalate to Pat.
5. **CPA spot-review at ≥5%**, stratified by chapter. Track reject rate; if any chapter exceeds 10%, pause synth for that chapter.
6. **Tag rows `synthetic_rationale: true`** so Vera can slice eval PASS/FAIL by provenance class. This is the most important field — without it, you cannot tell whether a regression is from the synth quality or from the model.

## §4 — Edie's rationale-shape table (parked for option B's prompt design)

Active only if option B triggers. Synthesized rationales must meet the **grader-coach minimum**: when the student answers wrong, the rationale must contain enough material for the model to coach the correction. A naked "**TRUE** — because GAAP" fails this bar.

### Per-Bloom × per-type rationale shape

| Bloom | TF | Matching |
|---|---|---|
| **Remember** | Citation only. *"TRUE — ASC 842-10-15-3 requires recognition of ROU assets for all leases exceeding 12 months."* One sentence, one standard. | *"Term X maps to definition 2 because both refer to the initial measurement of the lease liability at commencement — not the subsequent ROU asset amortization (definition 4)."* |
| **Understand** | Citation + the conceptual inversion that traps students. *"FALSE — students often read 'comprehensive income' as synonymous with 'net income'; ASC 220 distinguishes them by including OCI items (AFS unrealized gains, pension adjustments, cash-flow hedge gains) that bypass the income statement."* | Citation + the distinguishing criterion. *"The paired concepts share a surface label but differ on timing: X is at-commencement, Y is post-commencement."* |
| **Apply** | Show the predicate test. *"FALSE — the $200K direct cost IS capitalizable under ASC 350-40 because it meets the preliminary-project-stage vs. application-development-stage boundary: the cost was incurred after technological feasibility, so expense disqualification does not apply."* | Show the classification rule applied to each term. *"X→3: the cost fails the 'probable future benefit' criterion because … Y→1: the cost satisfies it because …"* |
| **Analyze / Evaluate** | Both candidate readings + the deciding criterion. *"At first reading TRUE: the lessee has contractual payments. FALSE: ASC 842 requires a separate assessment of whether the practical expedient for short-term leases (<12 months, no purchase option) was elected — without that election, the ROU asset must still be recognized."* | Competing-classification reasoning: *"Term X could map to either 2 or 4; the settling criterion is measurement date, not recognition event …"* |

### Grader-coach minimum (Edie's hard floor)

For a wrong TF answer, the rationale must name:

1. **The correct answer** (`TRUE` / `FALSE`).
2. **The standard that settles it** (ASC / FASB section, fully cited).
3. **The specific misconception the wrong answer reveals** (capitalize-vs-expense, allowance-vs-direct-write-off, operating-lease-on-balance-sheet, debit-vs-credit-on-accrual-reversal — see the well-known intermediate-accounting trap catalog).

A rationale that omits any of these three is not coaching-grade and should be rejected before SFT.

## §5 — Post-implementation checklist (Pat's standing rule, LLM-touching + data-touching → 11 extras)

LLM-touching changes get six extras:

- [ ] **Cost-per-turn estimate.** N/A for option A (no new LLM calls). Required if B triggers; surface a forecast before launch.
- [ ] **Cache topology.** N/A for A.
- [ ] **Model version pinned.** Required — `training_data_sha256` bumps to `spiceland9e-v1.2.0`. Base model pin unchanged.
- [ ] **Reasoning pattern named.** Unchanged from r0/r1/r2.
- [ ] **Failure-mode handlers.** N/A for A.
- [ ] **Hallucination guard.** A *strengthens* this by removing answer-only supervision. Vera adds a `by_rationale_presence` slice to the regression table.

Data-touching changes get five extras:

- [ ] **JSONL schema unchanged.** Filter is at split time, not canonical-JSONL time.
- [ ] **Noise rules unchanged.** The worked-solution filter is a split-time constant, not a new noise rule on the canonical layer.
- [ ] **Idempotency re-verified post-filter.** Re-running `split_multi_seed.py` on identical canonical input must produce byte-identical filtered splits.
- [ ] **Per-chapter stats re-logged.** The ~30% drop must be visible in `eval/stats/run_v1.2.0.json`; Diana documents which chapters lose the most rows (likely Ch.01-02 where TF concentrates).
- [ ] **Source-of-truth labels preserved.** `source_workbook` + `source_row` on every surviving record.

## §6 — Launch gate (Pat-owned)

Order is non-negotiable:

1. r1 executes on the DGX Spark row → `test_metrics.json` emitted.
2. r2 executes on the DGX Spark row → `test_metrics.json` emitted.
3. Vera runs `diff_runs.py` r1-vs-r0 and r2-vs-r0; Pat reviews both deltas + a small qualitative probe (does the model produce rationales now?).
4. **Decision branch**:
   - If r1 OR r2 produces rationales and lifts Apply ≥ tolerance → v1.2.0 **cancelled**, archived as "not needed".
   - Else → v1.2.0 **triggered**, Diana executes §1's acceptance criteria.

Trigger phrasing: *"Pat, gate-check v1.2.0 against the r1/r2 deltas."*

---

_Pinned dependencies today_: this plan is dormant; activation is gated on r1 + r2 outcomes. The lens fan-out that produced it is captured in the session transcript dated 2026-05-22. r0 baseline is `qwen3-4b-4bit-qlora-s00-r0` (69.2% on the 464-row scorable test split, bound to `spiceland9e-v1.1.0` / sha `fed6eb17de8be1e4…`).
