# GAAP corpus — provenance

**Verdict: PASS** — clean as-of date triangulated from three independent
signals (export timestamps, latest cited ASU, copyright year). One
chunking blocker flagged below; does not affect dating confidence.

---

**What this is.** FASB Accounting Standards Codification (ASC) snapshot,
the authoritative source of U.S. GAAP for this project.

**Source authority.** Financial Accounting Standards Board (FASB) —
https://asc.fasb.org/ (Financial Accounting Foundation copyright holder).

**Corpus form.** ASC topic-organized PDFs + paired publisher `.txt`
("Combine Sections" export — the FASB Codification Research System's
print-to-text feature). Each `.txt` carries the export timestamp on
line 1 and the section header on line 2.

**As-of date.** **Late January 2026** (export window 2026-01-24 through
2026-01-26 across all timestamped files). Strongest content signal:
ASU 2025-12 cited in multiple Broad Transactions and Assets subtopics —
corpus reflects ASUs issued through at least Q4 2025 / early 2026.

**Version / release.** "About the Codification" companion document is
**v 5.11 (February 2023)**, but this is the static reference guide;
the topic exports themselves are the late-Jan-2026 cut. Copyright line
on every clean export reads **"Copyright © 2026 by Financial Accounting
Foundation"** — confirms the 2026 vintage.

**File count.** 130 PDFs + 128 paired `.txt` (2 PDFs unpaired:
`Conceptual Framework for Financial Reporting (September 2024).pdf`
and `FASB_Special_Report-The_Framework_of_Financial_Accounting_Concepts_and_StandardsConceptual_Framework.pdf`).

**Corpus size.** 679 MB total (PDFs dominate).

**Topic coverage** (folder → ASC topic-range, evidence from filenames + status headers):

| Folder | ASC range | PDFs | .txt | Notes |
|---|---|---|---|---|
| General Principles | 105 | 1 | 1 | Single subtopic. **.txt garbled (cid-encoded).** |
| Presentation | 205, 210, 215, 220, 225, 230, 235, 250, 255, 260, 270, 272, 274, 275, 280 | 15 | 15 | **All 15 .txt files garbled (cid-encoded).** PDFs also fail `pdftotext`. |
| Assets | 305, 310, 320, 321, 323, 325, 326, 330, 340, 350, 360 | 11 | 11 | **10 of 11 .txt garbled** — only `360 Property, plant and equipment` is clean. |
| Liabilities | 405, 410, 420, 430, 440, 450, 460, 470, 480 | 9 | 9 | All clean. |
| Equity | 505 | 1 | 1 | Clean. |
| Revenue | 605, 606, 610 | 3 | 3 | Clean. ASC 606 carries ASU 2025-04 + 2025-07. |
| Expenses | 705, 710, 712, 715, 718, 720, 730, 740 | 8 | 8 | All clean. 718 carries ASU 2025-04; 720/730 carry ASU 2025-06. |
| Broad Transactions | 805, 808, 810, 815, 820, 825, 830, 832, 835, 840, 842, 845, 848, 850, 852, 853, 855, 860 | 18 | 18 | All clean. **Both ASC 840 (legacy) and ASC 842 (current) leases present** — solver must prefer 842 for post-2018 fact patterns. ASU 2025-12 cited in 815, 820, 825, 852. |
| Industry | 905, 908, 910, 912, 915, 920, 922, 924, 926, 928, 930, 932, 940, 942, 944, 946, 948, 950, 952, 954, 958, 960, 962, 965, 970, 972, 974, 976, 978, 980, 985, 995 | 41 | 41 | 32 base-topic .txt clean. **9 "Presentation of Financial Statements" satellites garbled** (905, 915, 946, 954, 958, 960, 962, 965, 972). |
| Master Glossary | A–Z (split alphabetically) | 20 | 20 | All clean. Defined-term source of truth. |
| (root) | Conceptual Framework x2 | 2 | 0 | Top-level conceptual docs, no paired .txt; PDFs are image-based (pdftotext returns junk). |

**Most-recent ASUs visible in the corpus** (strongest "as of" signal):
- **ASU 2025-12** — Assets (360), Broad Transactions (815, 820, 825, 852)
- **ASU 2025-11** — Assets (360), Broad Transactions (805, 810, 815, 820, ...)
- **ASU 2025-10** — Broad Transactions (805, 832, 845), Industry (958)
- **ASU 2025-07** — Broad Transactions (815), Revenue (606, 610)
- **ASU 2025-06** — Expenses (720, 730)
- **ASU 2025-04** — Expenses (718), Revenue (606)
- **ASU 2025-03** — Broad Transactions (805, 810, 815, 820, 842, ...)

Anything issued after January 2026 will NOT be in this corpus. Solver
should not assert authority on ASUs numbered 2026-XX.

**Authority order** (per user, 2026-05-20): This corpus is **newer than
the Spiceland test bank** at `data/Intermediate Financial Accounting
test bank/` and is **authoritative** for substantive accounting
correctness. The test bank's gold answers remain the eval target (Vera
scores against them) but the solver/tutor defer to current GAAP for
explanations and divergent-answer flagging. See
`.meta/sources_relationship.md` for the doctrine (to be authored).

**Retrieval-side notes** (Riley owns chunking):

- **Blocker — 35 unextractable files.** All Presentation/ (15),
  Assets/ 305–350 (10), Industry "Presentation of Financial Statements"
  satellites (9), and General Principles 105 (1) have `.txt` exports
  populated with `(cid:N)` glyph codes — the source PDFs were rendered
  with subset fonts and no ToUnicode CMap, so `pdftotext` also fails.
  Total impact: ~27% of files including the entirety of the
  Presentation topic (financial statements structure — high-value for
  Edie and Solomon). **Recommend re-acquisition via the FASB online
  Codification "Combine Sections" feature** before indexing; OCR is a
  fallback but will be lossy on numbered cross-references (e.g.
  "205-10-45-7" → "205-1O-45-7"). The two top-level Conceptual
  Framework PDFs are image-based and need OCR or a re-download.
- **Atomic-unit risk.** ASC paragraphs are addressed
  `Topic-Subtopic-Section-Paragraph` (e.g. `606-10-25-19`). Each
  paragraph is a chunkable atom; sub-paragraph fragmentation would
  destroy citation integrity. Status tables (ASU change-log at the top
  of every subtopic) are dense tables that should be skipped or chunked
  as a single atom — they read terribly when broken mid-row.
- **Defined-term cross-refs.** Master Glossary entries are short and
  cross-cut topics; they should be a distinct `chunk_class="glossary"`
  and retrieved on demand by Solomon when a term is recognized, not
  embedded into every topic chunk.
- **Legacy + current coexistence.** ASC 840 (superseded) and 842
  (current) are both present. Chunks must carry a `superseded_flag`
  metadata field so retrieval can suppress 840 unless the query is
  explicitly historical.
- **Industry "Presentation" stubs.** Where present, these are
  industry-specific overlays on Presentation topics, not standalone —
  treat as supplementary to the base topic file once de-garbling is
  resolved.

**Files inspected** (absolute paths):
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Revenue/606 Revenue from contracts with customers.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Broad Transactions/842 Leases.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Assets/326 financial instruments-credit losses.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Expenses/740 Income taxes.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Industry/944 Financail services-insurance.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Industry/958 Not-for-profit entitites.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Liabilities/470 Debt.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Equity/505 Equity.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Master Glossary/Master glossary 0-9 A-F.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/How to use codification.txt`
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Presentation/280 segment reporting.txt` (garbled — confirmed cid-encoded)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Presentation/210 Balance sheet.txt` (garbled)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/Assets/305 cash and cash equivalents.txt` (garbled)
- `/home/zi/Documents/GitHub/accounting/data/GAAP Data/General Principles/105 General Principles.txt` (garbled)

Full-corpus scan (Python regex over all 128 `.txt` headers + bodies)
extracted ASU references, export timestamps, and copyright years to
produce the cross-tables above.
