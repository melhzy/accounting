# Source corpora — test bank ↔ GAAP relationship doctrine

_Authored by Carla (CPA lens), grounded on Diana's + Riley's extracted dates (2026-05-20). Authoritative for the test-bank-vs-GAAP scoring + reasoning policy. See `data/Intermediate Financial Accounting test bank/PROVENANCE.md` and `data/GAAP Data/PROVENANCE.md` for the file-level publication evidence._

## 1. The two corpora at a glance

| | Test bank | GAAP corpus |
|---|---|---|
| Source | Spiceland *Intermediate Accounting*, 9th edition (Spiceland / Nelson / Thomas) | FASB Accounting Standards Codification |
| Path | `data/Intermediate Financial Accounting test bank/` | `data/GAAP Data/` |
| Vintage | **Copyright 2018**, drafted mid-2017 (Word `core.xml` shows authoring window 2017-08-09 → 2017-08-15); released August 2019 | **Late January 2026 export** (clean `.txt` timestamps 2026-01-24 → 2026-01-26, "© 2026 by Financial Accounting Foundation" on every export); latest cited ASUs **2025-12**; companion *Conceptual Framework for Financial Reporting* dated September 2024 |
| Role in project | **Eval target** — Vera scores against these gold answers | **Authoritative reference** — solver + tutor cite this |
| Coverage | 21 chapters, 4,453 questions, Bloom/AACSB/AICPA-tagged (active anchor `spiceland9e-v1.1.0`, sha256 `fed6eb17de8be1e4…`; retired `spiceland9e-v1.0.0` = `95f1ae448c693088…`, retired 2026-05-20) | 130 PDFs across 10 ASC topic clusters (Assets, Liabilities, Equity, Revenue, Expenses, Broad Transactions, Industry, Presentation, General Principles, Master Glossary); 128 paired `.txt` (93 clean / 35 garbled — see Riley's PROVENANCE) |

**The delta is ~8 years** (mid-2017 drafting → end-of-2025 ASUs). Long enough that every chapter has at least one nearby ASU; short enough that the foundational mechanics (ROU + lease liability, ASC 606 five-step) remain stable.

## 2. Why the gap matters (the accounting view)

The ~8-year delta between Spiceland 9e drafting (mid-2017, standards-frozen at that point) and ASC-as-of January 2026 (ASUs through 2025-12) spans these substantive changes. ASU-anchored and chapter-targeted:

- **ASU 2016-13 — Credit Losses (CECL), ASC 326**, fully effective for all entities by fiscal years beginning after 15 Dec 2022. Spiceland 9e still teaches the **incurred-loss** model for receivables; current GAAP requires the **expected-credit-loss** (lifetime ECL) model. Affects **Ch. 7 (Cash & Receivables)** most, with secondary impact on **Ch. 12 (Investments — HTM debt)**. **Highest-volume drift surface in the corpus.**
- **ASU 2017-04 — Goodwill Impairment Simplification, ASC 350-20**, effective public 2020 / private 2023. Eliminates **Step 2** of the goodwill impairment test; impairment now = carrying amount − fair value of reporting unit, capped at goodwill. Spiceland 9e illustrates the two-step approach. Affects **Ch. 11 (Intangibles)**.
- **ASU 2019-12 — Simplifying Income Taxes, ASC 740**, effective public 2020 / private 2021. Eliminates the exception to the incremental approach for intraperiod allocation and several other technical exceptions. Affects **Ch. 16 (Income Taxes)** worked examples.
- **ASU 2020-04 + ASU 2022-06 — Reference Rate Reform, ASC 848**. Optional expedients for contracts referencing LIBOR; sunset 31 Dec 2024. Spiceland 9e assumes LIBOR-indexed instruments in bond/derivative examples; the floor is now SOFR. Affects **Ch. 14 (Bonds)** illustrative cites.
- **ASU 2020-06 — Convertible Instruments, ASC 470 / ASC 815**, effective public 2022 / private 2024. **Significantly simplifies** convertible-debt accounting: eliminates the cash-conversion and beneficial-conversion separation models for most instruments. Also changes the **if-converted method** for diluted EPS. Affects **Ch. 14 (Bonds)** and **Ch. 18 (EPS)** — Spiceland 9e teaches the pre-2020-06 separation models that are now largely retired.
- **ASU 2023-07 — Segment Reporting Improvements, ASC 280**, effective fiscal years beginning after 15 Dec 2023. Adds disclosure of significant segment expenses. Affects any Spiceland chapter touching segment reporting (typically end-of-textbook).
- **ASU 2023-08 — Crypto Assets, ASC 350-60**, effective fiscal years beginning after 15 Dec 2024. Moves in-scope crypto from indefinite-lived intangible (cost less impairment, no upward writes) to **fair value through net income**. **Not in Spiceland 9e at all**; if a downstream question touches crypto holdings, the textbook is silent and current GAAP governs unilaterally.
- **ASU 2023-09 — Income Tax Disclosure Improvements, ASC 740**, effective public 2024 / private 2025. Adds disaggregated tax-rate-reconciliation and income-taxes-paid disclosure. Additive to Ch. 16 beyond ASU 2019-12.
- **ASU 2024-03 — Disaggregation of Income Statement Expenses, ASC 220**, effective fiscal years beginning after 15 Dec 2026. Forward-looking — corpus contains the standard but Spiceland predates and most current practice still does not reflect it. Flag as **future-state**.
- **ASU 2018-12 — Long-Duration Insurance Contracts, ASC 944**, effective 2023 for public filers. Out of Spiceland 9e's typical scope, but if a question touches insurance liabilities the textbook treatment is superseded.
- **Stabilized-since-9e (NOT divergence)**: ASC 842 leases (ASU 2016-02) and ASC 606 revenue (ASU 2014-09) both transitioned through Spiceland 9e drafting and are now post-transition. The textbook teaches the modern standards. Narrow-scope ASUs since (842: 2018-10/11/20, 2019-01, 2021-05, 2021-09, 2023-01 common-control; 606: 2016-08/10/11/12/20, 2021-08 contract assets in business combos) **refine but do not overturn** the recognition pattern.
- **Principle-preserved-even-if-example-superseded**: Spiceland's bad-debt-allowance worked examples illustrate the **right concept** (forward-looking estimate against a contra-asset) — CECL changes the *measurement* (lifetime expected loss vs. incurred-loss probable threshold) but preserves the *mechanism* (allowance contra-account, no direct write-off). The textbook's journal-entry pattern survives even when its triggering threshold does not.

## 3. Scoring policy (Vera reads this)

The test-bank gold answer remains the **scoring target** for three reasons: (a) reproducibility — every regression must compare against a frozen target, and Spiceland is the frozen target anchored by sha256 `fed6eb17de8be1e4…` (`spiceland9e-v1.1.0`, active 2026-05-20); (b) pedagogical alignment — students using Spiceland 9e expect Spiceland's expected answer; (c) backward-compatibility of the eval harness across model runs.

But the test-bank gold is NOT the final correctness call. Vera's harness must:

- When a model answer matches Spiceland but contradicts current GAAP, score it as `gold_match: true, gaap_aligned: false` rather than collapsing both into a single "correct" bit. The eval slice table needs both columns.
- Emit a per-question `gaap_divergence` flag in the slice table for any question where Carla has filed a divergence note. Aggregate `gaap_divergence` by chapter so Pat sees the drift surface at a glance — Ch. 7 (CECL), Ch. 11 (goodwill), Ch. 14 + Ch. 18 (convertibles), Ch. 16 (tax) will dominate.
- Never silently rewrite the gold. The divergence is a **second column**, not a replacement. Any proposal to overwrite the JSONL `answer` field hits the destruction gate and requires Pat sign-off plus Diana re-ingest plus Vera re-baseline.
- Regression rule: a model that *gains* `gaap_aligned: true` while holding `gold_match` steady is an improvement; a model that *loses* `gold_match` to chase `gaap_aligned` is a regression in the SFT phase (RAG/solver phase relaxes this).

## 4. Solver policy (Solomon reads this)

The solver should produce an answer that is **simultaneously test-bank-correct and GAAP-current** when possible. When they diverge:

- The solver answers the Spiceland question per Spiceland's expected answer first, then appends a delimited note: `Note: per ASU XXXX-XX (effective YYYY-MM-DD), this guidance was updated to <X>. Current GAAP would now require <Y>.` — with a Riley-retrieved cite from the GAAP corpus (`ASC <Topic>-<Subtopic>-<Section>-<Paragraph>`).
- Solver output schema gains a `gaap_supersession` block — `null` when no divergence, otherwise `{asu_number, effective_date, changed_paragraphs, modern_answer, citation, asc_pdf_path}`. The `asc_pdf_path` lets Vera and Edie click through to the exact source PDF.
- Tools that compute numbers (depreciation schedule, EPS, journal-entry validator, bond amortization) follow the **standard in effect at the time the question was authored** — i.e., Spiceland 9e vintage. The question's underlying facts and dates are fixed; the numeric answer should not change because GAAP later evolved. The `gaap_supersession` block describes how the *standard* changed, not how the *number* in this question changes.
- Exception: if a question explicitly tests a recognition trigger that has been deleted (e.g., a goodwill Step-2 measurement question post-ASU 2017-04, or a beneficial-conversion-feature bifurcation post-ASU 2020-06), the solver still computes the Spiceland-expected number but the supersession block flags `recognition_trigger_removed: true` so Edie can warn the student.

## 5. Tutor policy (Edie reads this)

Edie's tutoring output: lead with the Spiceland-expected answer (because the student is studying Spiceland and is being scored against Spiceland), then a clearly-delimited **"What's changed since this textbook was published"** section drawn from the `gaap_supersession` block. The pedagogy is: don't confuse the student during exam prep, but don't leave them with stale CPA knowledge either. The CPA exam blueprint moves faster than textbooks — students who only learn Spiceland 9e walk into the new FAR/discipline sections with gaps on CECL, goodwill simplification, convertibles simplification, and crypto.

## 6. Retrieval policy (Riley reads this)

Riley's retriever indexes both corpora, BUT:

- At retrieval time, score test-bank rationales and GAAP paragraphs in the **same recall pool**; surface the highest-scoring chunk from each as **separate citations** rather than concatenating. The student sees both provenance trails.
- A Spiceland citation is `(Chapter, LO, Topic)`; a GAAP citation is `(ASC Topic, Subtopic, Section, Paragraph)`. Both surfaced when present. Format: `Spiceland 9e Ch. 7 LO 07-05` and `ASC 326-20-30-1` side by side.
- If a Spiceland rationale cites a now-superseded standard (e.g., legacy ASC 840 leases, incurred-loss receivables, two-step goodwill, beneficial-conversion bifurcation), Riley's retriever must also pull the **superseding ASU's paragraph** from the GAAP corpus and attach it. The presence of both `840 Leases.pdf` and `842 Leases.pdf` in the corpus is the signal: route to 842 by default; surface 840 only when the question text explicitly anchors to pre-2019 facts.
- The Master Glossary PDFs are tie-breakers when terminology has shifted (e.g., "lease term," "performance obligation," "credit loss"). Always cite the Master Glossary entry alongside the substantive paragraph when the term itself has been redefined.
- **Garbled-text caveat** (per Riley's PROVENANCE): 35 of 128 `.txt` files in the GAAP corpus are unusable due to subset-font / no-ToUnicode-CMap rendering — including all 15 Presentation/ files (205-280) and 10 of 11 Assets/ files. **Until those 35 are re-acquired or OCR'd**, citation-side coverage is ~73% of the corpus. Affected topics: balance sheet, income statement, cash flows, EPS, segment reporting, error corrections (Presentation/); cash, receivables, all four investment topics, CECL, inventory, intangibles (Assets/). **This is a structural blocker** to indexing the highest-pedagogical-value sections of the GAAP corpus.

## 7. The five topics most at risk of drift (rank-ordered)

With the named ASU/ASC paragraph driving the divergence:

1. **Receivables impairment / credit losses on HTM debt — ASC 326 (CECL).** ASU 2016-13. Spiceland 9e teaches incurred-loss; GAAP-as-of-2026 mandates lifetime expected credit losses. Affects **Ch. 7 (Receivables)** and **Ch. 12 (HTM debt investments)**. **Highest-volume drift in the corpus** and one of the topics inside Riley's garbled `Assets/326*.pdf` — extra-blocking until re-acquisition.
2. **Convertible instruments and diluted EPS — ASC 470 / ASC 815 / ASC 260.** ASU 2020-06 (eliminates cash-conversion + beneficial-conversion separation; changes the if-converted method for diluted EPS). Spiceland 9e teaches the pre-2020-06 separation. Affects **Ch. 14 (Bonds)** and **Ch. 18 (EPS)** — two chapters at once.
3. **Goodwill impairment — ASC 350-20.** ASU 2017-04 eliminated Step 2; impairment = carrying amount − fair value of reporting unit, capped at goodwill. Spiceland 9e illustrates the two-step method. Affects **Ch. 11 (Intangibles)**.
4. **Income tax intraperiod allocation + disclosure — ASC 740.** ASU 2019-12 (simplifications) + ASU 2023-09 (disaggregated rate-recon disclosure). Removes the exception to the incremental approach; expands tax-paid disclosure. Affects **Ch. 16 (Income Taxes)** worked examples and disclosure scope.
5. **Crypto-asset measurement — ASC 350-60.** ASU 2023-08, effective fiscal years beginning after 15 Dec 2024. Not in Spiceland 9e. If any downstream question or user prompt invokes crypto, the textbook is silent and the GAAP corpus governs unilaterally. Affects **Ch. 11/12 (Intangibles / Investments)** by extension.

## 8. Open questions for Pat

- Should `gaap_aligned` factor into the loss function during SFT, or stay purely a post-hoc eval column? My recommendation: **post-hoc only during SFT phase**; revisit when Solomon's solver-loop and Riley's RAG land, because by then the model has tool access to the GAAP corpus and can be held to a higher bar.
- When the Spiceland gold itself is *demonstrably wrong* (not merely outdated, but contradicted by the standard in effect at Spiceland's own 2017 drafting) — does that escalate to a gold-key correction, or stay as a divergence note? My read: **divergence note unless Vera + Diana + Carla all sign**, with Pat as arbiter, per the destruction gate.
- Riley's 35 garbled GAAP files (entirely Presentation 205-280 + most of Assets 305-360) — re-acquire via FASB online Codification with a different print pipeline (Riley's recommendation, clean), OCR (faster but corrupts paragraph addresses like `205-10-45-7` → `205-1O-45-7`), or ship Phase-1 retrieval on the 93 clean files (~73% coverage) while re-acquisition is in flight? My read: **ship Phase-1 + queue re-acquisition** so retrieval doesn't block on a data-supply issue, but flag every "no-retrieval-available" hit in Riley's recall@5 report so the gap is visible.

---

## Version history

### `spiceland9e-v1.1.0` — active 2026-05-20

- **sha256**: `fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`
- **records**: 4,453 (unchanged from v1.0.0; additive schema only)
- **stats artifact**: `eval/stats/run_v1.1.0.json`
- **changes** (additive, no gold-key rewrites except the two approved overrides):
  - Added `meta` block on every record: `gaap_divergence` (bool),
    `asc_anchor` (`{topic, subtopic, section}` or null),
    `gaap_supersession` (`{asu_number, effective_date,
    modern_answer_hint, asc_pdf_path}` or null), `standards_smell`
    (list of `{label, span, source_field}`), `gold_status`
    (`"ok"` | `"publisher_ambiguous"` | `"table_only"`),
    `exclude_from_scoring` (bool).
  - **AACSB canonicalization**: 51 raw delimiter/order/typo variants
    collapsed to 7 canonical labels; emitted as `list[str]` per record
    (mirrors the existing AICPA discipline). Typo map applied
    deterministically (`Analytic` → `Analytical Thinking`,
    `Communicative` → `Communication`, `Critical Thinking` → `Reflective
    Thinking`).
  - **Carla's GAAP-divergence catalog applied to 296 records**:
    convertibles+EPS (ASU 2020-06) 123 records across Ch. 14 + Ch. 19;
    CECL (ASU 2016-13) 79 records across Ch. 7 + Ch. 12 HTM;
    income tax (ASU 2019-12 + ASU 2023-09) 54 records in Ch. 16;
    goodwill (ASU 2017-04) 40 records in Ch. 11. Convertibles count
    exceeds the plan §2 estimate (40-60) because Spiceland's Ch. 19
    diluted-EPS questions consistently invoke the if-converted method
    that ASU 2020-06 amended — the breadth is correct, not a
    false-positive cascade.
  - **12 standards-version smell triggers pre-computed**: 154 hits
    across 123 records. 70 records auto-flagged
    `meta.smell_review_needed: true` for Carla triage (Ch. 15
    operating-lease false positives where Spiceland 9e teaches ASC 842
    + Ch. 12 cost-method legacy mentions in current equity-method
    chapter).
  - **ch12_q0199**: gold_answer populated per Carla's CPA-verified
    proposal (life-insurance whole-life journal entries 1 and 2);
    `meta.gold_status: "ok"`. Logged as
    `recovered_from_table_per_carla_2026-05-20`.
  - **ch21_q0141**: ruled publisher-ambiguous by Pat 2026-05-20;
    `gold_answer: null`, `meta.gold_status: "publisher_ambiguous"`,
    `meta.exclude_from_scoring: true`,
    `meta.gold_unknown_reason: "ambiguous_legend_duplicate_not_reported_entries_1_and_5"`.
    Retained in retrieval corpus; excluded from SFT and from scoring.
- **byte-different from v1.0.0 by construction** (additive keys → new
  JSON serialization). Idempotency contract preserved within v1.1.0:
  back-to-back re-runs on byte-identical sources produce a
  byte-identical JSONL with sha `fed6eb17de8be1e4…`.

### `spiceland9e-v1.0.0` — retired 2026-05-20

- **sha256**: `95f1ae448c693088b893758ffd24f667aed08593bc107611c9af722ff8f54e4b`
- **records**: 4,453
- **stats artifact**: `eval/stats/run_20260520_033521.json`
- Initial cut from the audited Spiceland 9e Excel + Word ingest (10
  noise rules, deterministic sort, byte-stable JSONL). Superseded by
  v1.1.0's schema + AACSB + empty-answer + README re-baseline.

---

_This doctrine is the contract between Diana (data provenance), Riley (citation), Vera (scoring), Solomon (solver), Edie (tutor), and Carla (CPA correctness). When the contract changes, every consuming lens must read the new version. Pat signs off on changes._

---

**Relevant absolute paths:**
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/PROVENANCE.md` (Diana, test-bank dating evidence)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/PROVENANCE.md` (Riley, GAAP-corpus dating evidence + garbled-file inventory)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Broad Transactions/842 Leases.pdf` and `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Broad Transactions/840 Leases.pdf` (lease transition pair)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Assets/326 financial instruments-credit losses.pdf` (CECL — top drift surface; **currently in Riley's garbled set**)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Conceptual Framework for Financial Reporting (September 2024).pdf` (image-based per Riley; anchors GAAP-corpus upper-bound vintage even though `.txt` extraction failed)
- `/home/zi/Documents/GitHub/accounting/eval/spiceland9e.jsonl` (gold-answer JSONL; active anchor `spiceland9e-v1.1.0`, sha256 `fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`; retired `v1.0.0` = `95f1ae448c693088…`)
- `/home/zi/Documents/GitHub/accounting/.meta/sources_relationship.md` (this file)
