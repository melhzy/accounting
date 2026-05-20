# Standards-drift report — Spiceland 9e (2018) vs ASC corpus (Jan 2026)

_Synthesis of the gaps, impacts, and conflicts between the two source corpora in this repository. Cross-references `.meta/sources_relationship.md` (the doctrine), `data/Intermediate Financial Accounting test bank/PROVENANCE.md`, `data/GAAP Data/PROVENANCE.md`, and `.meta/v1_1_0_plan.md` (the catalog applied to `eval/spiceland9e.jsonl`). Authored 2026-05-20._

---

## 1. Executive summary

The Accounting LLM Framework consumes two source corpora that are **~8 years apart in vintage**:

- **Test bank** — Spiceland *Intermediate Accounting* 9e, copyright 2018, drafted mid-2017. Acts as the **eval target** (gold answers Vera scores against).
- **GAAP corpus** — FASB Accounting Standards Codification, late-January-2026 export, citing ASUs through ASU 2025-12 plus the September-2024 Conceptual Framework. Acts as the **authoritative reference** the solver and tutor cite.

Across that gap, **296 of 4,453 records (6.6%)** in `eval/spiceland9e.jsonl` carry `meta.gaap_divergence: true`. The drift is concentrated in four ASU clusters (convertibles+EPS, CECL, income taxes, goodwill) plus a fifth coverage gap (crypto). Foundational mechanics — debits=credits, ROU + lease-liability under ASC 842, the ASC 606 five-step model, FIFO/LIFO/Avg, PV/FV — remain stable across the delta.

**Project doctrine (per `.meta/sources_relationship.md`):** test-bank gold remains the scoring target; current GAAP governs substantive correctness. Divergence is surfaced as a **second column** (`gaap_aligned`), never as a silent gold rewrite.

---

## 2. The two corpora

|  | Test bank | GAAP corpus |
|---|---|---|
| Source | Spiceland / Nelson / Thomas, *Intermediate Accounting* 9e | FASB Accounting Standards Codification |
| Publisher | McGraw-Hill | Financial Accounting Foundation |
| Path | [data/Intermediate Financial Accounting test bank/](data/Intermediate Financial Accounting test bank/) | [data/GAAP Data/](data/GAAP Data/) |
| Vintage anchors | Word `footer1.xml` reads `Copyright ©2018 McGraw-Hill`; `docProps/core.xml` `created` dates 2017-08-09 → 2017-08-15 | `.txt` export timestamps 2026-01-24 → 2026-01-26; `Copyright © 2026 by Financial Accounting Foundation` on every clean export |
| Latest standards reflected | ASC 606 (revenue) and ASC 842 (leases) fully adopted; standards frozen at ~mid-2017 | ASUs through **ASU 2025-12**; companion *Conceptual Framework for Financial Reporting* dated September 2024 |
| Volume | 21 chapter pairs, **4,453 questions** (active anchor `spiceland9e-v1.1.0`, sha256 `fed6eb17…`) | 130 PDFs across 10 ASC topic clusters; 128 paired `.txt` (93 clean / 35 garbled) |
| Role | Eval target — Vera scores model output against the gold | Authoritative reference — solver + tutor cite this for substantive correctness |
| Question types | MC 2,153 / Essay-Problem 1,168 / Matching 706 / TF 426 | Codification paragraphs addressed `Topic-Subtopic-Section-Paragraph` (e.g. `606-10-25-19`) |

**Delta:** ~8 years. Long enough that every chapter has at least one nearby ASU. Short enough that recognition mechanisms (allowance accounts, ROU asset, contract-based revenue) survive even when measurement triggers move.

---

## 3. The gaps — ranked by record count

296 records flagged `meta.gaap_divergence: true`, distributed across four ASU clusters. The fifth gap (crypto) is a **coverage gap, not a divergence** — Spiceland 9e is silent.

### 3.1 Convertible instruments + diluted EPS — 123 records (largest count)

- **Driver:** ASU 2020-06, effective public 2022 / private 2024.
- **ASC paragraphs:** `ASC 470-20-25` (convertible debt recognition), `ASC 260-10-45` (EPS — if-converted method), `ASC 815-15-25` (embedded derivatives bifurcation).
- **Test-bank chapters affected:** Ch. 14 Bonds, Ch. 19 EPS.

**What Spiceland teaches:**
- **Cash-conversion separation model** — convertible debt with a cash-settlement feature is bifurcated into a liability component (PV of cash flows discounted at the nonconvertible rate) and an equity component (residual).
- **Beneficial-conversion-feature (BCF) allocation** — when the conversion option is in-the-money at issuance, the intrinsic value is allocated to APIC.
- **Original if-converted method** for diluted EPS, treating conversion as if it had occurred at the beginning of the period.

**What current GAAP requires:**
- Convertible debt is generally accounted for as a **single liability** (no separation) unless it meets narrow bifurcation criteria (substantial premium, embedded derivative requiring bifurcation under ASC 815).
- The cash-conversion and BCF separation models are **eliminated** for most instruments.
- **If-converted method amended** — preferred-dividend add-back behavior changed; some previously antidilutive instruments are now dilutive (and vice versa).

**Why this is the largest count (123, vs Carla's plan §2 estimate of 40–60):** Spiceland Ch. 19 (EPS) consistently invokes the if-converted method in worked examples, so any diluted-EPS question with a convertible component lands in this bucket. Breadth is correct; not a false-positive cascade.

**Conflict surface:** A model answering "use the cash-conversion separation to allocate $X to equity" matches the Spiceland gold but contradicts current GAAP. Per scoring policy, this scores `gold_match: true, gaap_aligned: false`.

### 3.2 Credit losses (CECL) — 79 records

- **Driver:** ASU 2016-13, fully effective for all entities by fiscal years beginning after 2022-12-15.
- **ASC paragraphs:** `ASC 326-20-30` (receivables — current expected credit losses), `ASC 326-30-30` (HTM debt).
- **Test-bank chapters affected:** Ch. 7 Cash & Receivables (primary), Ch. 12 Investments (HTM debt subset).

**What Spiceland teaches:**
- **Incurred-loss model** — recognize an allowance for credit losses only when a loss is "probable and reasonably estimable" (the SFAS 5 / ASC 450 threshold).
- Aging-of-receivables schedules tied to a historical-loss-rate percentage.
- HTM debt impairment using the "other-than-temporary impairment" framework.

**What current GAAP requires:**
- **Current expected credit loss (CECL) model** — recognize the **lifetime expected credit loss at origination** ("day-one reserve"), forward-looking, incorporating reasonable-and-supportable forecasts.
- HTM debt: same CECL framework, no longer the OTTI bright-line.

**What survives:** The **mechanism** — contra-asset allowance, no direct write-off, journal-entry pattern (`DR Bad debt expense / CR Allowance for doubtful accounts`) — is unchanged. The **trigger threshold** (incurred-loss → lifetime ECL) is what moved.

**Conflict surface:** A model citing "we wait until the loss is probable and estimable" matches Spiceland and contradicts current GAAP. Spiceland's specific aging-schedule worked answers still produce the right number for the question as written, because Spiceland fixes the historical-loss-rate inputs; current GAAP would compute a different number from forward-looking inputs the question does not provide.

**Structural blocker:** The GAAP-corpus file `Assets/326 financial instruments-credit losses.txt` is in Riley's **35-file garbled set** (cid-encoded, subset-font). The #1 drift surface currently has no retrievable GAAP citation until re-acquisition lands.

### 3.3 Income taxes — 54 records

- **Drivers:** ASU 2019-12 (simplifications), ASU 2023-09 (disclosure improvements).
- **ASC paragraphs:** `ASC 740-20-45` (intraperiod allocation), `ASC 740-10-50` (disclosure).
- **Test-bank chapter affected:** Ch. 16 Income Taxes.

**What Spiceland teaches:**
- The **exception to the incremental approach** for intraperiod allocation — under the old rule, total tax expense was first computed on continuing operations excluding certain items, with a partial reallocation back.
- Original disclosure scope (rate-reconciliation at the entity level).

**What current GAAP requires:**
- The intraperiod-allocation exception is **eliminated**; total tax is allocated to continuing operations on an incremental basis without the carve-out.
- **Disaggregated rate-reconciliation disclosure** (specified categories with quantitative thresholds) plus **income-taxes-paid disclosure** by jurisdiction.

**What survives:** Core DTA/DTL mechanics, the 21% TCJA federal rate, valuation-allowance logic, NOL carryforward rules (TCJA-era — indefinite carryforward, 80% taxable-income limitation). Worked deferred-tax problems still produce the right numbers.

**Conflict surface:** Limited to the intraperiod-allocation worked examples and disclosure-format questions. Mainstream DTA/DTL problems are unaffected.

### 3.4 Goodwill impairment — 40 records

- **Driver:** ASU 2017-04, effective public 2020 / private 2023.
- **ASC paragraphs:** `ASC 350-20-35`.
- **Test-bank chapter affected:** Ch. 11 Intangibles.

**What Spiceland teaches:**
- The **two-step** goodwill impairment test:
  - **Step 1:** compare reporting-unit carrying amount to fair value; if carrying > FV, proceed to Step 2.
  - **Step 2:** compare the carrying amount of goodwill to the **implied fair value of goodwill** (hypothetical purchase-price allocation).
- The qualitative "Step 0" assessment as an optional precursor.

**What current GAAP requires:**
- **Single-step** test: impairment = carrying amount of the reporting unit − fair value of the reporting unit, **capped at the goodwill balance**.
- Step 0 (qualitative) and Step 1 (the trigger) are unchanged.

**What survives:** The Step 0 qualitative assessment, the Step 1 trigger, the FV-of-reporting-unit measurement methodology, the post-impairment carrying amount.

**Conflict surface:** Any worked example invoking "implied fair value of goodwill" or "hypothetical purchase price allocation" is computing a number using deleted machinery. The Spiceland-gold number is the test-bank correct answer; current GAAP would either produce a smaller impairment (capped at goodwill) or skip the second computation entirely.

### 3.5 Crypto assets — 0 records flagged (coverage gap, not divergence)

- **Driver:** ASU 2023-08, effective fiscal years beginning after 2024-12-15.
- **ASC paragraph:** `ASC 350-60`.
- **Test-bank chapters affected:** None — Spiceland 9e is silent on crypto.

**What Spiceland teaches:** Nothing. The textbook predates crypto becoming a meaningful accounting topic.

**What current GAAP requires:** In-scope crypto assets are measured at **fair value through net income** (was: indefinite-lived intangible — cost less impairment, no upward writes).

**Why 0 records:** This is a coverage gap, not a divergence. No existing test-bank question references crypto, so there is nothing to flag in `eval/spiceland9e.jsonl`. If a downstream user prompt invokes crypto holdings, the textbook is silent and the GAAP corpus governs unilaterally.

---

## 4. Secondary drift (catalogued, lower volume)

| Drift | ASU / ASC | Spiceland status | Disposition |
|---|---|---|---|
| Reference rate reform — LIBOR → SOFR | ASU 2020-04 + ASU 2022-06 / ASC 848 (sunset 2024-12-31) | Spiceland assumes LIBOR-indexed bonds and derivatives | Pre-compute via the `LIBOR` smell trigger; surface but do not gate-fail |
| Segment reporting | ASU 2023-07 / ASC 280 (effective after 2023-12-15) | Spiceland teaches the pre-disaggregation disclosure model | Affects any chapter touching segments; typically end-of-textbook |
| Long-duration insurance contracts | ASU 2018-12 / ASC 944 | Out of Spiceland 9e's typical scope | Note-only; route through the GAAP corpus if a question touches insurance liabilities |
| Disaggregation of income statement expenses | ASU 2024-03 / ASC 220 (effective after 2026-12-15) | Spiceland predates; most current practice also does not reflect it | **Future-state**; corpus contains the standard but flag accordingly |
| Equity-method scope and AFS-equity reclassification | ASU 2016-01 / ASC 321 | Spiceland 9e was authored during this transition; pre-2016-01 cost-method language can leak into post-2016-01 equity-method chapters | Pre-compute via the `available-for-sale equity` and `cost method` smell triggers; manual triage |
| Income tax disclosure expansion | ASU 2023-09 / ASC 740-10-50 | Additive to Ch. 16 beyond 2019-12 simplifications | Bundled into the 54 Ch. 16 records counted above |

---

## 5. NOT drift — do not double-flag

These are commonly assumed to be drift surfaces but are stable across the test-bank ↔ GAAP delta:

- **ASC 842 Leases** (ASU 2016-02) — Spiceland 9e drafted **after** the standard was issued and teaches the modern ROU + lease-liability framework. Literal string "ASC 842" appears in Ch. 15 body text. Narrow-scope follow-on ASUs (2018-10, 2018-11, 2018-20, 2019-01, 2021-05, 2021-09, 2023-01 common-control) refine but do not overturn. **Diana's smell trigger over-fired here**: 70 records auto-flagged `meta.smell_review_needed: true` because the word "operating lease" appears without the modifier "right-of-use" / "ROU" — Spiceland uses both terms but does not pair them in every sentence.

- **ASC 606 Revenue** (ASU 2014-09) — Spiceland 9e teaches the 5-step model in Ch. 5. Post-publication ASUs (2016-08/10/11/12/20, 2021-08 contract assets in business combinations) refine but do not overturn.

- **Allowance-method mechanism** — CECL changes the *measurement* (lifetime ECL vs incurred-loss probable threshold) but preserves the *mechanism* (contra-asset allowance, no direct write-off, the journal-entry pattern). Spiceland's worked aging schedules still illustrate the right concept.

- **TCJA-era federal tax rate** (21%) — current and reflected in Spiceland 9e (TCJA enacted December 2017, Spiceland drafted mid-2017 but published with the rate). Ch. 16 worked examples remain right.

- **Inventory mechanics** — LIFO, FIFO, weighted-average, lower-of-cost-or-NRV (for non-LIFO under ASC 330). No material updates since publication.

- **Bond amortization** — effective-interest method, premium/discount amortization, retirement before maturity. Substantive rules stable; only LIBOR-vs-SOFR illustrative cites have aged.

---

## 6. Impacts — by stakeholder

### 6.1 Vera (eval / verifier)

- Slice table needs **two columns** per question: `gold_match` (matches Spiceland's expected answer) and `gaap_aligned` (consistent with current GAAP). Never collapse into one.
- Aggregate `gaap_divergence` by chapter so the drift surface is visible at a glance:

  | Chapter | Topic | Records flagged |
  |---|---|---|
  | Ch. 7 | Receivables (CECL) | ~70 |
  | Ch. 11 | Goodwill (single-step) | 40 |
  | Ch. 12 | HTM debt (CECL) | ~9 |
  | Ch. 14 | Convertibles (separation) | ~60 |
  | Ch. 16 | Income taxes (intraperiod / disclosure) | 54 |
  | Ch. 19 | Diluted EPS (if-converted) | ~63 |

  (Counts inside CECL and convertibles split across chapters per the divergence catalog in `.meta/v1_1_0_plan.md` §2.)

- **Regression rule:** model that gains `gaap_aligned: true` while holding `gold_match` steady → improvement. Model that loses `gold_match` to chase `gaap_aligned` → regression in the SFT phase. RAG/solver phase relaxes this.
- **One record excluded entirely:** `ch21_q0141` (`meta.exclude_from_scoring: true`) — publisher-ambiguous, retained in retrieval corpus.

### 6.2 Solomon (solver)

- **Answer-the-question first, supersede-second** ordering: produce Spiceland's expected answer, then append the delimited `gaap_supersession` block when applicable.
- Output schema gains a `gaap_supersession` field on every record: `null` when no divergence, otherwise `{asu_number, effective_date, changed_paragraphs, modern_answer, citation, asc_pdf_path}`.
- **Tools that compute numbers follow the standard in effect at question-authoring time** (Spiceland 9e vintage). The depreciation schedule does not change because GAAP later evolved; the supersession block describes how the *standard* changed, not how the *number in this question* changes.
- **Exception:** when a question explicitly tests a deleted recognition trigger (e.g. goodwill Step-2, BCF allocation), the solver still computes the Spiceland-expected number but flags `recognition_trigger_removed: true` for Edie.

### 6.3 Edie (tutor)

- Lead with the Spiceland-expected answer (student is being scored against Spiceland), then a clearly delimited **"What's changed since this textbook was published"** section drawn from the `gaap_supersession` block.
- **Pedagogy rationale:** don't confuse the student mid-exam-prep; don't leave them with stale CPA knowledge either. The CPA exam blueprint moves faster than textbooks — Spiceland-only learners will hit gaps on CECL, goodwill simplification, convertibles simplification, and crypto in the new FAR/discipline sections.
- Bloom-level scaffolding: Remember/Understand questions get the supersession note as a footnote; Apply/Analyze/Evaluate questions get it as a side-by-side comparison.

### 6.4 Riley (retrieval)

- Index **both corpora** in the same recall pool. Surface the highest-scoring chunk from each as **separate citations** — never concatenate.
- Citation formats:
  - Spiceland: `Spiceland 9e Ch. 7 LO 07-05` (chapter + learning objective)
  - GAAP: `ASC 326-20-30-1` (topic-subtopic-section-paragraph)
- When a Spiceland rationale cites a superseded standard, pull the **superseding ASU's paragraph** from the GAAP corpus and attach it.
- **Legacy + current coexistence:** both `ASC 840 Leases` (superseded) and `ASC 842 Leases` (current) are present in the corpus. Chunks must carry a `superseded_flag` so retrieval suppresses 840 unless the query explicitly anchors to pre-2019 facts.
- **Master Glossary as tie-breaker:** when terminology has shifted (e.g. "credit loss," "lease term," "performance obligation"), cite the Master Glossary entry alongside the substantive paragraph.
- **Structural blocker — 35 garbled GAAP files** (cid-encoded, subset-font, no ToUnicode CMap): all 15 Presentation/ files (205-280), 10 of 11 Assets/ files (305-350), 9 Industry "Presentation of Financial Statements" satellites, and General Principles 105. Coverage ~73% until re-acquisition. **Includes `Assets/326*.pdf` (CECL) — the #1 drift surface is in the unusable set.**

### 6.5 Diana (data / ETL)

- Owns the `meta` block emission per record: `gaap_divergence`, `asc_anchor`, `gaap_supersession`, `standards_smell`, `gold_status`, `exclude_from_scoring`.
- Owns the divergence-catalog filter (chapter + LO + topic + prompt-text regex) that populates `gaap_divergence: true` on 296 records.
- Owns the smell-trigger pre-compute (12 patterns, see §7 below).
- v1.1.0 active anchor: `spiceland9e-v1.1.0`, sha256 `fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`. v1.0.0 retired 2026-05-20 (`95f1ae44…`).

### 6.6 Carla (CPA correctness)

- Owns the drift catalog and the supersession-note templates (4 slot-filled templates: CECL, convertibles+EPS, goodwill, taxes — see [.meta/v1_1_0_plan.md §2](.meta/v1_1_0_plan.md)).
- Owns the "what survives" judgment for each ASU (mechanism vs measurement vs disclosure).
- Owns the divergence-vs-coverage-gap distinction (crypto is a gap, not a flagged divergence).

### 6.7 Pat (PM / arbiter)

- Owns the **destruction gate** on any proposal to silently rewrite the test-bank gold. Approved overrides so far: 2 (ch12_q0199 gold recovery; ch21_q0141 exclude-from-scoring).
- Owns the regression rule (above) and the loss-weighting call for SFT: **0.85 gold / 0.15 supersession-note** (tightened from Carla's original 0.7/0.3 to avoid over-weighting the ~6.6% drift slice).

---

## 7. Standards-version smell triggers

12 regex patterns pre-computed by Diana into `meta.standards_smell` and consumed by Vera's `mechanical_checks.py`:

| # | Pattern | Pre-standard | Drift class |
|---|---|---|---|
| 1 | `risks and rewards` (transfer of) | pre-ASC 606 | revenue legacy |
| 2 | `operating lease` AND NOT (`right-of-use` OR `ROU`) | pre-ASC 842 | lease legacy (high false-positive rate in Spiceland Ch. 15) |
| 3 | `extraordinary item(s)` | pre-ASU 2015-01 | income-statement legacy |
| 4 | `incurred loss` / `probable and estimable` (receivables context) | pre-CECL (ASU 2016-13) | ASC 326 drift |
| 5 | `two-step` / `Step 2` / `implied fair value of goodwill` | pre-ASU 2017-04 | goodwill drift |
| 6 | `beneficial conversion` / `BCF` / `cash conversion feature` | pre-ASU 2020-06 | convertibles drift |
| 7 | `LIBOR` (without `SOFR` or `reference rate reform`) | pre-ASU 2020-04 / 2022-06 | rate-reform stale |
| 8 | `available-for-sale equity` / `AFS equity` | pre-ASU 2016-01 | equity-investment legacy |
| 9 | `cost method` (equity investments, non-consolidation) | pre-ASU 2016-01 | equity-investment legacy |
| 10 | `pooling of interests` | pre-SFAS 141 (2001) | sanity check (should never fire) |
| 11 | `completed-contract method` (as default, not policy choice for short contracts) | pre-ASC 606 emphasis | revenue legacy |
| 12 | `direct write-off method` (asserted as GAAP, not tax) | always-wrong | **hard FAIL** trigger |

**Hit volume (v1.1.0):** 154 hits across 123 records. 70 records auto-flagged `meta.smell_review_needed: true` for Carla triage — concentrated in:

- **Ch. 15 lease false-positives** (Spiceland teaches ASC 842 but uses the unmodified phrase "operating lease" in places).
- **Ch. 12 cost-method legacy mentions** in the current equity-method chapter (Spiceland 9e was authored during the ASU 2016-01 transition).

Smell-review triage is Carla's responsibility; Diana surfaces, Carla rules.

---

## 8. Conflict-resolution policy

When test-bank gold and current GAAP diverge, the system resolves the conflict as follows:

### 8.1 Scoring (Vera)

- **The Spiceland gold remains the scoring target.** Three reasons:
  - **Reproducibility** — regressions compare against a frozen target, anchored by sha256 `fed6eb17…`.
  - **Pedagogical alignment** — students using Spiceland 9e expect Spiceland's expected answer.
  - **Backward compatibility** of the eval harness across model runs.
- A model answer that matches Spiceland but contradicts current GAAP scores `gold_match: true, gaap_aligned: false` — both columns, never collapsed.
- **Never silently rewrite the gold.** Divergence is a second column. Any proposal to overwrite the JSONL `answer` field hits the destruction gate: Pat sign-off + Diana re-ingest + Vera re-baseline.

### 8.2 Reasoning (Solomon)

- Produce both: the Spiceland-expected answer first, then the supersession note.
- Numbers follow Spiceland-era standards (the question's facts and dates are fixed); the supersession describes how the *standard* changed, not how the *number* changes.

### 8.3 Pedagogy (Edie)

- Lead with Spiceland (exam-prep alignment), follow with "what's changed."
- Bloom-level scaffolding: footnote for Remember/Understand; side-by-side comparison for Apply+.

### 8.4 Citation (Riley)

- Surface both citations: `Spiceland 9e Ch. X LO X-XX` + `ASC X-XX-XX-X`.
- When the Spiceland citation references a superseded standard, attach the superseding ASU paragraph.
- Master Glossary entries cited alongside the substantive paragraph when terminology has shifted.

### 8.5 Gold-key correction (rare exception)

When the Spiceland gold itself is **demonstrably wrong** (not merely outdated — contradicted by the standard in effect at Spiceland's own 2017 drafting):
- Default disposition: **divergence note**, not gold rewrite.
- Override path: Vera + Diana + Carla all sign; Pat arbitrates per the destruction gate.
- **Two such corrections so far:**
  - `ch12_q0199` — gold recovered from publisher table per Carla CPA-verified proposal (life-insurance whole-life journal entries).
  - `ch21_q0141` — ruled publisher-ambiguous by Pat (ambiguous legend duplicate); `gold_answer: null`, excluded from scoring, retained in retrieval.

---

## 9. Structural caveats

### 9.1 The 35 garbled GAAP files

Per [data/GAAP Data/PROVENANCE.md](data/GAAP Data/PROVENANCE.md), 35 of 128 `.txt` files in the GAAP corpus are **cid-encoded** — rendered with subset fonts and no ToUnicode CMap, so `pdftotext` returns glyph codes (`(cid:N)`) rather than letters. Affected:

- All 15 **Presentation/** files (ASC 205-280): balance sheet, income statement, cash flows, EPS, segment reporting, error corrections — high pedagogical value, currently unusable.
- 10 of 11 **Assets/** files (ASC 305-350): cash, receivables, all four investment topics, **CECL (326)**, inventory, intangibles.
- 9 **Industry** "Presentation of Financial Statements" satellites.
- General Principles 105.

**Coverage impact:** ~27% of files; the **#1 drift surface (CECL) is in the unusable set**. Until re-acquisition, citation-side coverage is ~73% of the corpus.

**Open question for Pat** (per [.meta/sources_relationship.md §8](.meta/sources_relationship.md)): re-acquire via FASB online Codification with a different print pipeline (Riley's recommendation, clean), OCR (faster but corrupts numbered cross-references like `205-10-45-7` → `205-1O-45-7`), or ship Phase-1 retrieval on the 93 clean files while re-acquisition is in flight. Carla's read: **ship Phase-1 + queue re-acquisition** so retrieval doesn't block on a data-supply issue, but flag every "no-retrieval-available" hit in Riley's recall@5 report.

### 9.2 Two image-based PDFs

The two top-level Conceptual Framework documents (`Conceptual Framework for Financial Reporting (September 2024).pdf` and `FASB_Special_Report-The_Framework_of_Financial_Accounting_Concepts_and_StandardsConceptual_Framework.pdf`) have no paired `.txt` and are image-based. Needs OCR or re-download.

### 9.3 Forward-looking standards in the corpus

The 2026-vintage GAAP corpus includes standards effective **after** the corpus's own as-of date:
- **ASU 2024-03** (income statement disaggregation, ASC 220) — effective fiscal years beginning after 2026-12-15.

Solver / tutor should not assert this as currently-required practice; flag as **future-state**.

### 9.4 Standards issued after late January 2026

Anything issued after the corpus export window (2026-01-26) is **not in the GAAP corpus**. Solver must not assert authority on ASUs numbered `2026-XX` or later.

---

## 10. Agent awareness — current gap

The doctrine in this report (and in [.meta/sources_relationship.md](.meta/sources_relationship.md)) is **not yet wired into the agent prompts** at [.claude/agents/](.claude/agents/). As of 2026-05-20:

- Zero agent prompt files reference `sources_relationship.md`, `gaap_divergence`, `asc_anchor`, `gaap_supersession`, `standards_smell`, or `exclude_from_scoring`.
- Agents have generic GAAP / Spiceland-9e knowledge but no awareness of the 8-year vintage skew or the 296-record divergence catalog.

**Ownership split (recommended):**

| Concern | Owner | Status |
|---|---|---|
| Doctrine authorship + drift catalog | Carla | Doctrine written; agent prompt not updated |
| `meta.*` schema fields, 296-record flag | Diana | Schema designed in v1.1.0 plan; agent prompt not updated |
| Scoring rule (gold = target even when GAAP-divergent), `exclude_from_scoring` plumbing | Vera | Policy decided; agent prompt not updated |
| Answer-then-supersede output structure | Solomon + Edie | Templates drafted in §2 of v1.1.0 plan; agent prompts not updated |
| Ship gate ("Carla flagged divergence not addressed" → blocker) | Pat | Policy decided; agent prompt not updated |

Next action: patch each agent prompt with a doctrine-anchor paragraph naming `.meta/sources_relationship.md` and the agent's slice of the responsibility.

---

## 11. Appendix — sources

**File-level evidence:**

- [data/Intermediate Financial Accounting test bank/PROVENANCE.md](data/Intermediate Financial Accounting test bank/PROVENANCE.md) — Diana, test-bank dating evidence (2018 copyright, mid-2017 drafting, sha anchors).
- [data/GAAP Data/PROVENANCE.md](data/GAAP Data/PROVENANCE.md) — Riley, GAAP-corpus dating evidence (Jan 2026 export, ASUs through 2025-12, 35 garbled files).
- [.meta/sources_relationship.md](.meta/sources_relationship.md) — Carla, conflict-resolution doctrine (the contract between Diana, Riley, Vera, Solomon, Edie, Carla; Pat signs off on changes).
- [.meta/v1_1_0_plan.md](.meta/v1_1_0_plan.md) — Pat, v1.1.0 implementation plan (the divergence catalog, the 12 smell triggers, the supersession-note templates, the loss-weighting call).

**Eval-artifact evidence:**

- [eval/spiceland9e.jsonl](eval/spiceland9e.jsonl) — canonical gold corpus; active anchor `spiceland9e-v1.1.0`, sha256 `fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`.
- `eval/stats/run_v1.1.0.json` — reconciling stats artifact for the v1.1.0 anchor.
- `eval/diana_warnings.log` — ETL warnings (47 entries) plus `_v1_1_0_changelog` block.

**Key ASC paragraphs (citation targets when GAAP-aligned):**

- `ASC 326-20-30` (receivables — CECL), `ASC 326-30-30` (HTM debt — CECL)
- `ASC 350-20-35` (goodwill impairment — single-step post-2017-04)
- `ASC 350-60` (crypto assets — fair value through net income)
- `ASC 470-20-25` (convertible debt — single liability post-2020-06)
- `ASC 260-10-45` (EPS — if-converted method amended)
- `ASC 740-20-45` (intraperiod allocation — exception eliminated)
- `ASC 740-10-50` (income tax disclosure — disaggregated rate-recon)
- `ASC 280` (segment reporting — significant segment expenses post-2023-07)
- `ASC 220` (income statement disaggregation — future-state, effective 2027+)
- `ASC 848` (reference rate reform — LIBOR sunset)
