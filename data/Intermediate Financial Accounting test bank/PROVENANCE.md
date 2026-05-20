# Test bank — provenance

**Verdict: PASS.** Edition, copyright year, and publisher all extracted
directly from the source artifacts. ISBN is not embedded in the files
and is reported below as derived/known (Spiceland 9e canonical ISBN),
not as a file-extracted fact.

**What this is.** Spiceland *Intermediate Accounting* test bank, 21
chapters, used in this project as the eval corpus and (eventually) the
SFT training source. Excel sheets are the structured ingest input;
matching Word docs are the publisher's original answer key narrative
and serve as the fallback for truncated/empty `Answer` cells.

**Edition.** *Intermediate Accounting, 9e (Spiceland).* Evidence: every
chapter's `word/document.xml` opens with the literal string
`Intermediate Accounting, 9e (Spiceland) Chapter N <title>` as the
running page header (verified in Ch01, Ch05, Ch15, Ch21).

**Copyright year.** **2018.** Evidence: `word/footer1.xml` in every
sampled chapter contains `Copyright ©2018 McGraw-Hill` (Ch01, Ch05,
Ch15). The Word `.docx` `docProps/core.xml` also records authorship by
"Denise" in **August 2017** (Ch01 created 2017-08-14, Ch05 2017-08-15,
Ch15 2017-08-15, Ch21 2017-08-09 — consistent with a publisher's
pre-publication production cycle for a 2018-copyright textbook released
in calendar 2019). The 2026-dated `core.xml` timestamps on the `.xlsx`
files are our downstream openpyxl re-emit, not source provenance.

**Publisher.** **McGraw-Hill** (footer evidence above; also corroborated
by the Spiceland 9e public catalog record).

**ISBN.** Not present in the source files. Canonical ISBN-13 for
Spiceland *Intermediate Accounting*, 9e (print, hardcover) is
**978-1-259-72266-0**; this is reported as derived knowledge, not
file-extracted, and should be verified against a physical copy before
citing in a publication.

**Authors.** J. David Spiceland, Mark W. Nelson, Wayne B. Thomas
(Spiceland 9e author team; the `.docx` `dc:creator` field reads
"Denise", which is a production-editor credential, not the textbook
author).

**As-of standards vintage.** Authored 2017, published as 2018-copyright
9th edition.
- ASC 606 (Revenue from Contracts with Customers) — **fully adopted**
  in Ch. 5; the chapter is titled "Revenue Recognition" and teaches the
  5-step model.
- ASC 842 (Leases) — **fully adopted** in Ch. 15; literal "ASC 842"
  string present in body text. ASC 842 was effective for public
  business entities for fiscal years beginning after Dec 15 2018, so
  the test bank teaches the new standard.
- ASC 326 (CECL) — at most partial; CECL was effective for PBEs
  beginning after Dec 15 2019 and would not have been a teaching
  centerpiece in a 2018-copyright edition.
- ASU 2023-08 (crypto), ASU 2022-04 (supplier finance disclosure),
  ASU 2021-08 (contract assets in business combinations), ASU 2020-04
  (reference rate reform) — **all post-publication; not reflected.**

**Corpus statistics** (from `eval/stats/run_v1.1.0.json`).
- 21 chapter pairs (`.docx` answer keys + `.xlsx` processed test banks).
- **4,453** canonical questions.
- **Active anchor `spiceland9e-v1.1.0`** —
  `sha256 fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`
  (cut 2026-05-20).
- **Retired anchor `spiceland9e-v1.0.0`** —
  `sha256 95f1ae448c693088b893758ffd24f667aed08593bc107611c9af722ff8f54e4b`
  (_retired_at: 2026-05-20; superseded by v1.1.0 schema additions).
- By type: Multiple Choice 2,153 / Essay-Problem 1,168 / Matching 706 /
  True-False 426.
- By difficulty: 2-Medium 2,062 / 1-Easy 1,296 / 3-Hard 1,057 /
  unlabeled 38.
- By Bloom's (after dual-label split): Apply 1,547 / Understand 1,216 /
  Remember 1,107 / Analyze 556 / Evaluate 38 / Create 18.
- AACSB canonicalized v1.1.0 → 7 canonical labels (down from 51 raw
  variants): Analytical Thinking, Communication, Diversity, Ethics,
  Knowledge Application, Reflective Thinking, Technology. Typo map:
  `'Analytic' → 'Analytical Thinking'`, `'Communicative' → 'Communication'`,
  `'Critical Thinking' → 'Reflective Thinking'`. Multi-label rows split
  on `'; '` and `', '` then deduped and sorted alphabetically (mirrors
  the AICPA discipline).
- v1.1.0 `meta` block on every record: `gaap_divergence`, `asc_anchor`,
  `gaap_supersession`, `standards_smell`, `gold_status`,
  `exclude_from_scoring`. **296 records flagged
  `gaap_divergence: true`** by Carla's drift catalog
  (`/.meta/sources_relationship.md`): convertibles+EPS (ASU 2020-06)
  123, CECL (ASU 2016-13) 79, tax (ASU 2019-12) 54, goodwill
  (ASU 2017-04) 40. **123 records hit at least one of the 12
  standards-version smell triggers**; 70 also carry
  `meta.smell_review_needed: true` flagging current-GAAP-correct
  Ch.15 lease / Ch.12 cost-method false-positive triage candidates.
- ETL warnings (47 entries in `eval/diana_warnings.log`): 18 header-
  artifact rows dropped, 10 MC->Essay reclassifications, 6 Word answer
  fallbacks, 4 options-bleed nulls, 3 explanation-metadata strips
  (Ch15), 2 ID collisions disambiguated, 2 hand-curated overrides
  (ch12_q0199 recovered_from_table_per_carla_2026-05-20;
  ch21_q0141 publisher_ambiguous_per_pat_2026-05-20 with
  `meta.exclude_from_scoring: true`).

**Known limitations** (relative to current GAAP, as of 2026-05-20):
- **Ch. 5 Revenue.** ASC 606 core model is current, but narrow-scope
  ASUs since 2018 (e.g., ASU 2021-08 on contract assets/liabilities in
  business combinations) are not reflected.
- **Ch. 15 Leases.** ASC 842 core model is current; post-2018 practical
  expedient and disclosure ASUs are not reflected.
- **Ch. 9 Inventory.** LIFO and lower-of-cost-or-NRV mechanics are
  durable; no material updates since publication.
- **Ch. 14 Bonds / Ch. 16 Income Taxes / Ch. 18 Shareholders' Equity.**
  Substantive rules stable; TCJA-era tax rate of 21% is current and
  reflected.
- **Ch. 12 Investments.** Pre-CECL framing; impairment guidance in
  questions may not match current ASC 326-based expected-loss model.
- **Crypto, supplier finance, reference rate reform.** Not present.

**Authority order** (per user, 2026-05-20). The GAAP corpus at
`/home/zi/Documents/GitHub/accounting/data/GAAP Data/` is newer
(includes the FASB *Conceptual Framework for Financial Reporting*
**September 2024**) and is authoritative for substantive correctness.
When the test bank's expected answer conflicts with current GAAP, the
**test bank gold remains the eval target** (Vera scores against it) but
the **solver and tutor should defer to current GAAP** for substantive
correctness, citing both. See Riley's
`data/GAAP Data/PROVENANCE.md` for the GAAP as-of date and
`.meta/sources_relationship.md` for the conflict-resolution policy
(both forward references; create alongside this file if missing).

**Source files referenced** (all absolute paths).
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/word/Spiceland9e_Chapter01_TB_AnswerKey.docx`
  — `docProps/core.xml` (creator=Denise, created 2017-08-14),
  `word/footer1.xml` (`Copyright ©2018 McGraw-Hill`),
  `word/document.xml` (header literal "Intermediate Accounting, 9e
  (Spiceland) Chapter 1 …").
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/word/Spiceland9e_Chapter05_TB_AnswerKey.docx`
  — same footer copyright; body covers ASC 606 5-step model.
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/word/Spiceland9e_Chapter15_TB_AnswerKey.docx`
  — body contains literal "ASC 842" (lease standard vintage anchor).
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/word/Spiceland9e_Chapter21_TB_AnswerKey.docx`
  — `docProps/core.xml` created 2017-08-09.
- `/home/zi/Documents/GitHub/accounting/data/Intermediate Financial Accounting test bank/excel/Spiceland9e_Chapter01_TB_AnswerKey_Processed.xlsx`
  — `docProps/core.xml` shows openpyxl re-emit on 2026-02-17 (downstream
  processing, NOT source provenance).
- `/home/zi/Documents/GitHub/accounting/eval/spiceland9e.jsonl`
  — canonical ingest output, **v1.1.0** active anchor
  `sha256 fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`,
  4,453 records. v1.0.0 retired hash
  `sha256 95f1ae448c693088b893758ffd24f667aed08593bc107611c9af722ff8f54e4b`
  (retired_at: 2026-05-20; superseded by v1.1.0 schema additions —
  meta block, AACSB canonicalization, ch12_q0199 recovered gold,
  ch21_q0141 publisher-ambiguous resolution).
- `/home/zi/Documents/GitHub/accounting/eval/stats/run_v1.1.0.json`
  — reconciling stats artifact for the v1.1.0 anchor (rows_in==rows_kept;
  per-chapter / per-Bloom / per-Difficulty / per-type counts; drift
  distribution by ASU; AACSB canonical label inventory).
- `/home/zi/Documents/GitHub/accounting/eval/diana_warnings.log`
  — 47 ETL warnings + `_v1_1_0_changelog:` block at the top naming every
  changed cell.
