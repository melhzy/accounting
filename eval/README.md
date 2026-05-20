# `eval/` — Spiceland 9e training corpus

End-to-end pipeline that converts the Spiceland 9e test bank (21 Word `.docx`
+ 21 Excel `.xlsx` files under
[`data/Intermediate Financial Accounting test bank/`](../data/Intermediate%20Financial%20Accounting%20test%20bank/))
into SFT-ready chat-template training data for fine-tuning.

**Word is the authoritative source.** When the Excel disagrees with Word
(LO text missing, MC mislabels, etc.), Word wins.

## See also

- [`.meta/sources_relationship.md`](../.meta/sources_relationship.md) —
  doctrine governing the relationship between the Spiceland test-bank
  gold (eval target) and the FASB ASC GAAP corpus (substantive
  authority). Diana and Carla co-author. Pat signs off.
- [`data/Intermediate Financial Accounting test bank/PROVENANCE.md`](../data/Intermediate%20Financial%20Accounting%20test%20bank/PROVENANCE.md)
  — test-bank dating evidence, ISBN, ASU coverage limits, corpus stats.
- [`data/GAAP Data/PROVENANCE.md`](../data/GAAP%20Data/PROVENANCE.md)
  — GAAP corpus as-of date, ASU citations, garbled-file inventory.

## Provenance & authority order

- Test bank corpus: `data/Intermediate Financial Accounting test bank/`
  — Spiceland *Intermediate Accounting* 9th ed., ©2018 McGraw-Hill,
  drafted mid-2017. See
  `data/Intermediate Financial Accounting test bank/PROVENANCE.md`.
- GAAP corpus: `data/GAAP Data/` — FASB Accounting Standards
  Codification, late-January 2026 export, ASUs through 2025-12. See
  `data/GAAP Data/PROVENANCE.md`.
- **Doctrine**: see `.meta/sources_relationship.md`. Test-bank gold
  remains the eval target; the GAAP corpus is authoritative for
  substantive correctness. The solver emits a structured
  `meta.gaap_supersession` block on the ~296 drift-affected questions
  at training and inference time. The 12 standards-version smell
  triggers in `meta.standards_smell` are pre-computed at ingest;
  Vera's `eval/mechanical_checks.py` (forthcoming) consumes them at
  eval time.
- **Current pin**: `spiceland9e-v1.1.0`, sha256
  `fed6eb17de8be1e493b1a54277bdb70175502e517ea4cd4e6877914f437d213b`.
  The previous `v1.0.0 = 95f1ae448c693088…` is retired 2026-05-20. All
  5 SFT seed splits re-emit from this anchor.

## Layout

```
eval/
  README.md                          ← you are here
  _format.py                         shared chat-template rendering helpers
  _audit/                            diagnostic scripts + audit reports

  extract_word_tables.py             stage 1
  ingest_spiceland.py                stage 2
  split_multi_seed.py                stage 3 (production)

  spiceland9e_tables.jsonl           stage 1 output (1,687 Word tables)
  spiceland9e.jsonl                  stage 2 output (4,453 canonical records)
  diana_warnings.log                 stage 2 warnings (45 entries)
  stats/run_<ts>.json                stage 2 lineage (sha256 + per-rule counts)

  sft/splits/                        stage 3 output
    manifest.json                    overall index of all seeds
    seed_<i>__<seed_int>/
      train.jsonl                    80%
      valid.jsonl                    10% (use for early-stopping / LR schedule)
      test.jsonl                     10% (held out for post-training eval)
      manifest.json                  per-seed stats
```

## Pipeline

Run from repo root. Each stage is idempotent — byte-identical output across
re-runs given byte-identical inputs.

```powershell
python eval/extract_word_tables.py    # ~10 s
python eval/ingest_spiceland.py       # ~15 s
python eval/split_multi_seed.py       # ~5 s
```

| Stage | Reads | Writes | Purpose |
|------:|-------|--------|---------|
| 1 | Word `.docx` (21 files) | `spiceland9e_tables.jsonl` | Extract JE / amortization / financial-statement tables in document order, stitch to parent question via monotonic Q# tracking |
| 2 | Excel `.xlsx`, Word `.docx`, `spiceland9e_tables.jsonl` | `spiceland9e.jsonl`, `stats/run_*.json`, `diana_warnings.log` | Apply 10 noise rules (Bloom-fallback, LO Excel-internal lookup, Word-explanation fallback, MC mislabel reclassification, …) and emit a canonical JSONL keyed on disambiguated IDs |
| 3 | `spiceland9e.jsonl` | `sft/splits/seed_*/...` | Multi-seed (default 5) scenario-grouped Bloom-stratified 80/10/10 split with deterministic seeds from `seedhash` |

## Output schema

### `spiceland9e.jsonl` (canonical, v1.1.0)

```jsonc
{
  "id": "ch05_q0084_mc",                // disambiguated by question type
  "chapter": 5,
  "question_number": 84,
  "type": "Multiple Choice",            // mc / tf / ma / es
  "prompt": "Companies recognize revenue only when:",
  "options": ["A: ...", "B: ...", "C: ...", "D: ..."],
  "gold_answer": "C",
  "explanation": "The key to revenue recognition is transfer of control...",
  "bloom": ["Apply"],                   // list — dual labels split here
  "difficulty": "2 Medium",
  "lo": {"code": "05-09", "text": "..."},
  "topic": "...",
  "aacsb": ["Knowledge Application"],   // v1.1.0: canonicalized list[str]
  "aicpa": ["BB Industry", "FN Measurement"],
  "tables": [...],                      // from spiceland9e_tables.jsonl
  "source_workbook": "...",
  "source_row": 86,
  "meta": {                             // v1.1.0 — every record carries this
    "gaap_divergence": false,           // true for ~296 drift-affected records
    "asc_anchor": null,                 // {topic, subtopic, section} | null
    "gaap_supersession": null,          // {asu_number, effective_date, modern_answer_hint, asc_pdf_path} | null
    "standards_smell": [],              // list of {label, span, source_field}
    "gold_status": "ok",                // "ok" | "publisher_ambiguous" | "table_only"
    "exclude_from_scoring": false       // true for ch21_q0141
  }
}
```

### `sft/splits/seed_NN__<seed_int>/{train,valid,test}.jsonl`

```jsonc
{
  "messages": [
    {"role": "system",    "content": "..."},
    {"role": "user",      "content": "[Chapter 5 · LO 05-09 · ...]\n\n..."},
    {"role": "assistant", "content": "**C**\n\nExplanation: ..."}
  ],
  "meta": {
    "id": "ch05_q0084_mc",
    "chapter": 5, "question_number": 84, "type": "Multiple Choice",
    "bloom": ["Apply"], "primary_bloom": "Apply", "difficulty": "2 Medium",
    "lo_code": "05-09", "topic": "...",
    "has_tables": true, "n_tables": 2, "has_explanation": true,
    "scenario_id": "8f3a...",            // shared by all sub-Qs of a multi-part scenario
    "scenario_group_size": 4,
    "has_worked_solution": true,         // filter on this for reasoning-focused training
    "assistant_length": 312,
    "source_workbook": "...", "source_row": 86
  }
}
```

## Fine-tuning workflow

Each `seed_NN__<seed_int>/` is an independent 80/10/10 partition. Train
once per seed, report `mean ± std` of test performance across seeds:

```python
from pathlib import Path
from datasets import load_dataset

for seed_dir in sorted(Path("eval/sft/splits").glob("seed_*")):
    ds = load_dataset("json", data_files={
        "train": str(seed_dir / "train.jsonl"),
        "valid": str(seed_dir / "valid.jsonl"),
        "test":  str(seed_dir / "test.jsonl"),
    })
    # Optional: reasoning-only subset (drops TF / Matching stubs)
    # ds["train"] = ds["train"].filter(lambda r: r["meta"]["has_worked_solution"])

    # Apply tokenizer.apply_chat_template(messages) at training time.
    # Use ds["valid"] for early-stopping / LR scheduling.
    # Evaluate on ds["test"] AFTER training, never during.
```

The split contract:
- `train` + `valid` are visible to the trainer.
- `test` is held out — touching it during training defeats the variance
  estimate the multi-seed setup provides.

## Configuration knobs

In `eval/split_multi_seed.py`:

| Constant | Default | Effect |
|----------|---------|--------|
| `SEEDHASH_INPUT` | `"spiceland9e-finetune-robustness-2026-05-19"` | Change to regenerate a fresh deterministic seed sequence |
| `N_SEEDS` | `5` | More seeds → tighter variance estimate, more training runs needed |
| `SPLIT_FRACTIONS` | `{"train": 0.80, "valid": 0.10, "test": 0.10}` | Must sum to 1.0 |
| `TOKENIZER_PIN` | `None` | Fill before fine-tune (e.g. `"Qwen/Qwen2.5-7B-Instruct@<git-sha>"`) |

## Auditing

Diagnostic scripts and audit reports live in [`_audit/`](_audit/). They are
investigation tools — not required for the production pipeline:

```
_audit/
  audit_all.py                  21-chapter audit (corpus stats, noise-rule firings)
  audit_report.{md,json}        latest audit output
  tables_extraction_report.{md,json}
  profile_one.py                single-chapter Excel + Word profiler
  probe_*.py                    targeted diagnostics from the data-quality session
```

Re-run an audit:

```powershell
python eval/_audit/audit_all.py
```

## What's documented elsewhere

- **Spiceland 9e Excel quirks** (schema variants by chapter, hidden columns,
  Q# collisions, option format, codepoint inventory) — see the
  `spiceland9e-excel-quirks` memory.
- **Pipeline rationale and design decisions** — see the
  `spiceland9e-data-pipeline` memory.

## Known limits of the source data

| Subset | What it lacks | Workaround |
|--------|---------------|------------|
| Ch.01 MC (80 records) | No worked-solution rationale in either Excel or Word | Filter on `meta.has_worked_solution` to drop, or accept letter-only labels |
| TF (426 records) | Answer is inherently `TRUE`/`FALSE` | Filter or use completion-only loss mask |
| Matching (706 records) | Answer is inherently `1`/`2`/… | Filter or use completion-only loss mask |
| Ch.02-04 MC | 20–33% worked-rate | Acceptable; falls within Bloom-stratified samples |
