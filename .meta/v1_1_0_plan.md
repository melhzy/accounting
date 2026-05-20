# `spiceland9e-v1.1.0` — implementation plan (staged for Diana)

_Pat-arbiter v1.1.0 scope, ratified by user 2026-05-20. Two gates cleared: (a) Carla's ch12_q0199 gold approved as-proposed; (b) v1.1.0 scope = schema + AACSB + empty-answers + README in one coordinated re-baseline. Diana executes when triggered. **Do not run yet** — Pat-sign-off destruction-gate CONFIRM cleared, but kickoff is on the user._

## Acceptance criteria (Diana → Vera → Pat)

The v1.1.0 corpus PASSES when:

- [ ] `eval/spiceland9e.jsonl` has a new sha256, recorded as the **`spiceland9e-v1.1.0` anchor** in `.meta/sources_relationship.md` and `data/Intermediate Financial Accounting test bank/PROVENANCE.md` (current v1.0.0 anchor `95f1ae448c693088…` retired with explicit `_retired_at: 2026-05-20`).
- [ ] All 4,453 records carry a `meta` block with the 5 new fields populated per §1 below.
- [ ] AACSB canonicalization reduces the unique value set from 51 → ≤ 15 canonical labels, emitted as `list[str]` per record (mirrors existing AICPA `"; "` split).
- [ ] ch12_q0199 has gold populated per Carla's approved proposal.
- [ ] ch21_q0141 has `meta.gold_status: "publisher_ambiguous"` and `meta.exclude_from_scoring: true`; row remains in corpus.
- [ ] `eval/diana_warnings.log` rewritten — `_v1_1_0_changelog:` block at the top names every changed cell.
- [ ] `eval/stats/run_v1.1.0.json` produced; row reconciliation passes (`rows_in == rows_kept`).
- [ ] All 5 SFT split sets re-emitted under `eval/sft/splits/seed_*/`; each per-seed manifest + top-level manifest carries the new v1.1.0 sha.
- [ ] `eval/README.md` has top-of-file "See also" linking `.meta/sources_relationship.md` + both PROVENANCE files, plus an "Authority order" paragraph mirroring `data/Intermediate Financial Accounting test bank/PROVENANCE.md` §11.
- [ ] Vera's `eval/mechanical_checks.py` (when authored — out of v1.1.0 scope but tracked here for r0) consumes the new `meta.standards_smell` field and runs the 12 patterns from §3 below.

## §1 — Schema additions to `eval/spiceland9e.jsonl`

New `meta` block on every record. **All fields default to null/false/[] for the ~4,228 non-drift records** so payload growth stays ~3 KB.

```jsonc
{
  // ... existing canonical fields (id, chapter, type, prompt, options[], gold_answer, rationale, bloom, difficulty, lo, topic, aacsb, aicpa, source_workbook, source_row) ...
  "meta": {
    "gaap_divergence": false,           // true for the ~155-225 drift-affected records
    "asc_anchor": null,                 // {topic, subtopic, section, paragraph} | null
    "gaap_supersession": null,          // {asu_number, effective_date, modern_answer_hint, asc_pdf_path} | null
    "standards_smell": [],              // pre-computed Vera smell-trigger hits (see §3)
    "gold_status": "ok",                // "ok" | "publisher_ambiguous" | "table_only"
    "exclude_from_scoring": false       // true for ch21_q0141
  }
}
```

**Idempotency**: schema is additive at the semantic layer (gold target unchanged); byte-different at file layer because keys are added → **v1.0.0 sha invalidates by construction**. This is expected and documented in the PROVENANCE update.

## §2 — Carla's GAAP-divergence catalog (populates `meta.gaap_divergence` + `meta.asc_anchor` + `meta.gaap_supersession`)

Apply by chapter + LO + topic filter:

| # | Drift topic | Spiceland Ch. | Filter (Diana grep) | ~Count | `asc_anchor` |
|---|---|---|---|---|---|
| 1 | CECL receivables / HTM debt | Ch. 7 (+ Ch. 12 HTM subset) | `chapter==7` AND `topic` ∈ {`Uncollectible`, `Receivables`, `Bad debt`, `Allowance`, `Notes receivable`}; `lo.number` ∈ {`07-04`,`07-05`,`07-06`,`07-07`} ∪ Ch. 12 `lo.number==12-08` | 80-100 | `{topic:326, subtopic:20, section:30}` for receivables; `{topic:326, subtopic:30, section:30}` for HTM |
| 2 | Convertibles + diluted EPS | Ch. 14 + Ch. 19 | Ch. 14 + `topic` ∈ {`Convertible`, `Induced conversion`, `Beneficial conversion`}; Ch. 19 + `topic` ∈ {`Diluted EPS`, `If-converted`, `Convertible securities`}; OR `prompt` contains `convertible` / `if-converted` | 40-60 | `{topic:470, subtopic:20, section:25}` + `{topic:260, subtopic:10, section:45}` |
| 3 | Goodwill two-step | Ch. 11 | `chapter==11` AND `topic` ∈ {`Goodwill`, `Impairment of goodwill`}; `lo.number` ∈ {`11-08`, `11-09`}; OR `prompt` contains `Step 1`/`Step 2`/`implied fair value of goodwill` | 15-25 | `{topic:350, subtopic:20, section:35}` |
| 4 | Tax intraperiod + disclosure | Ch. 16 | `chapter==16` AND `topic` ∈ {`Intraperiod`, `Valuation allowance`, `Rate reconciliation`, `Disclosure`}; `lo.number` ∈ {`16-08`, `16-09`} | 20-35 | `{topic:740, subtopic:20, section:45}` + `{topic:740, subtopic:10, section:50}` |
| 5 | Crypto (additive, no Spiceland coverage) | — none — | (n/a; coverage gap not divergence; do not flag any existing question) | 0 | n/a |

### Supersession-note templates (slot-filled into `meta.gaap_supersession.modern_answer_hint`)

**CECL (Ch. 7 / Ch. 12 HTM):**
> Note: per ASU 2016-13 (effective fiscal years beginning after 2022-12-15 for all entities), the incurred-loss model was replaced by the current expected credit loss (CECL) model requiring lifetime expected credit losses at origination. Current GAAP: ASC 326-20-30 (receivables) and ASC 326-30-30 (HTM debt). Spiceland teaching on the allowance-account mechanism remains correct; the measurement trigger ("probable + estimable" incurred-loss threshold) is superseded by day-one lifetime ECL.

**Convertibles + EPS (Ch. 14 / Ch. 19):**
> Note: per ASU 2020-06 (effective public 2022, all others 2024), the cash-conversion and beneficial-conversion-feature separation models were eliminated for most convertible debt; instruments are accounted for as a single liability unless they meet specific bifurcation criteria. The diluted-EPS if-converted method was also amended. Current GAAP: ASC 470-20-25 and ASC 260-10-45. Spiceland's pre-2020-06 separation and BCF allocation is superseded.

**Goodwill (Ch. 11):**
> Note: per ASU 2017-04 (effective public 2020, private 2023), Step 2 of the goodwill impairment test was eliminated. Impairment is now measured directly as the excess of the reporting unit's carrying amount over its fair value, capped at the goodwill balance. Current GAAP: ASC 350-20-35. Spiceland's two-step illustration is superseded; the qualitative assessment (Step 0) and Step 1 trigger remain correct.

**Income taxes (Ch. 16):**
> Note: per ASU 2019-12 (simplifications) and ASU 2023-09 (disclosure), the exception to the incremental approach for intraperiod allocation was eliminated and disaggregated rate-reconciliation + income-taxes-paid disclosures were added. Current GAAP: ASC 740-20-45 and ASC 740-10-50. Spiceland's worked intraperiod examples invoking the deleted exception are superseded; deferred-tax-asset/liability mechanics remain correct.

These four notes (slot-filled with the actual ASC paragraph anchors per record) emit at training time via `_format.py` template-bound logic — **no free-text generation of ASU numbers**, eliminating Diana's hallucination concern.

## §3 — Standards-version smell triggers (populate `meta.standards_smell` per record)

Pre-compute by case-insensitive regex over `gold_answer` + `rationale` + `tables[].markdown` + `explanation`. Surfaces hit-substrings; Vera's `mechanical_checks.py` consumes the field at eval time.

| Pattern | Pre-standard | Drift class |
|---|---|---|
| `risks and rewards` (transfer of) | pre-ASC-606 | revenue legacy |
| `operating lease` AND not `right-of-use` / `ROU` | pre-ASC-842 | lease legacy |
| `extraordinary item(s)` | pre-ASU 2015-01 | income-statement legacy |
| `incurred loss` / `loss has been incurred` / `probable and estimable` (in receivables context) | pre-CECL (2016-13) | ASC 326 drift |
| `two-step` / `Step 2` / `implied fair value of goodwill` | pre-ASU 2017-04 | goodwill drift |
| `beneficial conversion` / `BCF` / `cash conversion feature` | pre-ASU 2020-06 | convertibles drift |
| `LIBOR` (without `SOFR` or `reference rate reform`) | pre-ASU 2020-04/2022-06 | rate-reform stale |
| `available-for-sale equity` / `AFS equity` | pre-ASU 2016-01 | equity-investment legacy |
| `cost method` (for equity investments, non-consolidation) | pre-ASU 2016-01 | equity-investment legacy |
| `pooling of interests` | pre-SFAS 141 (2001) | sanity check |
| `completed-contract method` (asserted as default, not policy choice for short contracts) | pre-ASC-606 emphasis | revenue legacy |
| `direct write-off method` (asserted as GAAP, not tax) | always-wrong | hard FAIL |

## §4 — AACSB canonicalization (51 variants → canonical set)

Apply the same `"; "` split discipline as AICPA (per `eval/ingest_spiceland.py` noise rule §4). Strip whitespace; title-case; dedupe; sort alphabetically; emit `aacsb: list[str]`. Variants currently observed include `"Reflective Thinking, Diversity"` vs `"Reflective Thinking; Diversity"` (pure delimiter), `"Communication, Reflective Thinking"` vs `"Reflective Thinking; Communication"` (order), and typos `'Analytic'` / `'Knowledge application'` / `'Communicative'` — map typos to closest canonical.

Canonical labels (Spiceland's AACSB set, ≤ 15): `Analytical Thinking`, `Communication`, `Diversity`, `Ethics`, `Reflective Thinking`, `Technology`, plus any others Diana confirms by full inventory.

## §5 — Empty-answer items

**ch12_q0199 — APPROVED by user 2026-05-20.** Lift Carla's CPA-verified gold into `gold_answer`:

> (1) DR Insurance expense 81,000 / DR Cash surrender value of life insurance 14,000 / CR Cash 95,000.
> (2) DR Cash 6,000,000 / CR Cash surrender value of life insurance 70,000 / CR Gain on life insurance settlement 5,930,000.

Set `meta.gold_status: "ok"`, `meta.exclude_from_scoring: false`. Log in `diana_warnings.log` as `recovered_from_table_per_carla_2026-05-20`.

**ch21_q0141 — RULED publisher-ambiguous by Pat 2026-05-20.** Leave `gold_answer: null`; set `meta.gold_status: "publisher_ambiguous"`, `meta.exclude_from_scoring: true`, `meta.gold_unknown_reason: "ambiguous_legend_duplicate_not_reported_entries_1_and_5"`. Keep in eval corpus for retrieval reasoning; exclude from SFT and from scoring. Log in `diana_warnings.log` and document in `eval/README.md` provenance section.

## §6 — `eval/README.md` doctrine refresh

Top-of-file addition:

```markdown
## Provenance & authority order

- Test bank corpus: `data/Intermediate Financial Accounting test bank/` — Spiceland *Intermediate Accounting* 9th ed., ©2018 McGraw-Hill, drafted mid-2017. See `data/Intermediate Financial Accounting test bank/PROVENANCE.md`.
- GAAP corpus: `data/GAAP Data/` — FASB Accounting Standards Codification, late-January 2026 export, ASUs through 2025-12. See `data/GAAP Data/PROVENANCE.md`.
- **Doctrine**: see `.meta/sources_relationship.md`. Test-bank gold remains the eval target; GAAP corpus is authoritative for substantive correctness. Solver emits a structured `meta.gaap_supersession` block on the ~155-225 drift-affected questions at training and inference time.
- **Current pin**: `spiceland9e-v1.1.0`, sha256 `<new sha>` (the previous `v1.0.0 = 95f1ae448c693088…` is retired 2026-05-20). All 5 SFT seed splits re-emit from this anchor.
```

## §7 — Idempotency chain (strict order; destruction-gate CONFIRM cleared)

1. `eval/ingest_spiceland.py` — add `meta` block emission, AACSB canonicalizer, `gold_status` logic, supersession-template slot-fill from Carla's catalog (§2), smell-trigger pre-compute (§3)
2. `eval/spiceland9e.jsonl` — re-emit (NEW sha) — Diana commits with `_v1_1_0_changelog` header in `diana_warnings.log`
3. Update `data/Intermediate Financial Accounting test bank/PROVENANCE.md` with new sha + v1.1.0 anchor + `_retired:` line for v1.0.0
4. Update `.meta/sources_relationship.md` — replace `95f1ae44…` references with the v1.1.0 anchor, add a `## Version history` block at the bottom
5. `eval/stats/run_v1.1.0.json` — produced; row reconciliation passes
6. `eval/diana_warnings.log` — rewritten with v1.1.0 changelog (CONFIRM-gate per Diana's agent file)
7. `eval/split_multi_seed.py` — re-runs; seed manifests stay deterministic (same `seedhash` input), but row CONTENTS change because of new `meta`; emit fresh `eval/sft/splits/seed_*/manifest.json` + top-level `manifest.json` with v1.1.0 sha pins
8. `eval/README.md` — doctrine + provenance + sha block update (§6)
9. **Vera re-baseline** — once §1-8 land, Vera's `eval/run.py --baseline` (when it exists) anchors to v1.1.0; until then the SFT splits ARE the eval corpus for the notebook §12-§13 path

## Out-of-scope for v1.1.0 (tracked separately)

- The 35 garbled GAAP PDFs (Riley's earlier ask) — separate decision
- Dual-column scoring policy (`gold_match` + `gaap_aligned`) — Vera implementation question
- `eval/run.py` + `eval/diff_runs.py` + `eval/mechanical_checks.py` extraction — Vera's pre-r0 scaffolding ask
- Notebook fork to `models/recipes/dgx_spark/` — Leo's option-(c) recommendation, awaiting user gate

## Loss-weighting note (for r0 training, downstream of v1.1.0)

Pat's call: **0.85 gold / 0.15 supersession-note** (tightened from Carla's 0.7/0.3). Reasoning: the 155-225 drift slice over-weights against 4,228 non-drift questions at 0.3; at 0.15 the model learns the template emission without drifting toward parroting on Bloom-Remember Spiceland-only questions. Leo + Vera revisit at r1 once RAG is in scope.

---

**Status:** Ready for Diana kickoff. User-triggered. Pat sign-off documented above. No work begins on this plan without explicit user "go."

**Trigger phrasing:** "Diana, execute the v1.1.0 plan at `.meta/v1_1_0_plan.md`."
