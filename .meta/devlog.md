# Accounting LLM — Development Log

_Append-only chronological record of work done. Pat synthesizes the
ROADMAP from this. Each entry: date, lens (who owned it), what shipped,
non-obvious decisions._

---

## 2026-05-19 — Session 1 · Foundation

### Environment + agent roster

- **Conda env list cleanup** (huang/system). The `~/.conda/environments.txt` registry was emitting duplicate entries with mixed case (`C:\…` and `c:\…` for the same path). Conda treated them as distinct; Windows resolved them to the same dir. Deduped case-insensitively, normalized drive letters to uppercase. Pruned 7 ghost entries. Backup at `~/.conda/environments.txt.bak`.
- **Leo joins the roster** (Leo-LLM, 8th lens). New agent file at `.claude/agents/leo-llm.md`. Scope: base-model selection, fine-tuning recipes, serving stack, quantization, tokenizer/context-window discipline, cost/latency tradeoffs. Gap identified: Solomon owns prompts, Riley owns embeddings, but no one owned the model substrate.
- **GAAP Data ingest path**: noted but deferred. `data/GAAP Data/` contains the full FASB ASC (~130 PDFs + paired `.txt`, 679 MB). Decision: implement as a separate ingest stream when retrieval (Riley) is wired up; not in scope for the SFT pipeline.

### Data audit (Diana lens)

- **Excel test bank validated against Word source** (Spiceland 9e, 21 chapter pairs). Built profile + audit scripts under `eval/_audit/`.
- **Headline findings**:
  - 4,453 canonical questions across 21 chapters, ~99.8% answer-complete for MC/TF/Matching, 99.3% for Essay/Problem.
  - 18 header-artifact rows (drop on ingest). 66 dual-Bloom labels. 4 options-bleed rows.
  - **Schema drift across chapters** — 11 / 12 / 13 / 14 columns depending on chapter group. Extra cols are `Explanation` (worked solutions, ch.06-21), `Question Type` (redundant), `Blooms` (no apostrophe — used in ch.08-09 as fallback), `Option` (exact dup of Options).
  - **1,687 Word tables** (JEs, amortization schedules, financial statements) attached to questions. The Excel converter flattened ~54% of them into text — **the Word `.docx` is the authoritative source for tables**.
  - **228 LO code-only rows** recoverable via an Excel-internal `code → text` map (sibling rows have the full LO text; 100% recovery, no Word needed).
  - **746 records gained worked solutions from Word `Explanation:` paragraphs** that the Excel didn't have. Ch.05 MC worked-rate jumped from 0% → 86%.
  - **10 MC mislabels reclassified to Essay/Problem** (`Question_Type='Multiple Choice'` but answer is a multi-paragraph worked solution).
  - **Inherent limits**: Ch.01 MC (80 records) has no rationale in either Excel or Word. TF (426) and Matching (706) are inherently single-token answers.

### Pipeline (Diana → Riley → Leo overlap)

Three-stage idempotent pipeline at `eval/`:

1. `extract_word_tables.py` → `spiceland9e_tables.jsonl` (1,687 tables, 0 orphans, monotonic Q# tracking)
2. `ingest_spiceland.py` → `spiceland9e.jsonl` (4,453 canonical records with all noise rules applied)
3. `split_multi_seed.py` → `eval/sft/splits/seed_<i>__<int>/{train,valid,test}.jsonl` × 5 seeds

**Shared renderer** at `eval/_format.py` (extracted during consolidation — was duplicated across `build_training_set.py` and `split_multi_seed.py`; the former was deleted as the multi-seed splitter is now the production path).

### Leo's HOLD-then-PASS review

Leo reviewed the initial 90/5/5 single-split and flagged two ship-blockers:
1. **Scenario-grouped leakage** — `sha1(record_id)` per-record assignment scattered multi-question scenarios (e.g. Cupid Construction Q#185-188) across train/holdout, inflating holdout accuracy.
2. **44% stub assistant messages** — model would learn `**X**` output shape instead of reasoning.

Both fixed:
- Scenario-grouped split (3,424 scenarios, fingerprint = sha1 of first 300 normalized prompt chars after stripping `N)` marker + "Use this information…" preamble). Cross-split overlap **= 0** in every seed.
- `meta.has_worked_solution` tag on every record; trainer can filter or loss-mask.
- Word `Explanation:` paragraph recovery added → 746 records flipped stub→worked.

### Splits — 80/10/10 × 5 seeds

Switched to **5 deterministic seeds** via the `seedhash` package
(`SEED_HASH_INPUT = "spiceland9e-finetune-robustness-2026-05-19"`).
Each seed produces an independent 80/10/10 partition that respects scenario
grouping and Bloom stratification (modal Bloom per scenario). All 5
verified idempotent (sha256 stable across re-runs) and 0 cross-split
scenario overlap.

| seed | train | valid | test |
|------|------:|------:|-----:|
| 00 (351199285) | 3,537 | 450 | 464 |
| 01 (1884065545) | 3,540 | 453 | 458 |
| 02 (1805455021) | 3,535 | 452 | 464 |
| 03 (880639735) | 3,553 | 467 | 431 |
| 04 (1797866777) | 3,558 | 448 | 445 |

### Consolidation pass

`eval/` cleaned up — `__pycache__/` removed, obsolete single-split outputs
deleted (`eval/sft/{train,dev,holdout}.jsonl`), stats pruned to most-recent
run, `eval/_audit/` kept as diagnostic tooling. Added `eval/README.md` and
project-root `.gitignore`.

### Memories saved

For future sessions:
- `spiceland9e_excel_quirks` — schema variants by chapter, hidden columns, Q# collisions, option format, codepoint inventory.
- `spiceland9e_data_pipeline` — three-stage idempotent ETL design, key implementation details.

---

## 2026-05-20 — Session 2 · Fine-tune setup

### Hardware probe

Workstation (see [.meta/hardware.md](hardware.md)):

- **CPU** Intel i9-13900HX (24c / 32t)
- **GPU** RTX 4090 Laptop, 16 GB, sm_89 (Ada)
- **RAM** 64 GB DDR5-5600
- **Storage** 105 GB free on `C:`, 167 GB free on `D:` (where the project lives)
- **OS** Windows 11 Home build 26200

### Python envs

| Env | Python | Role |
|-----|--------|------|
| system | 3.13.3 | Data pipeline scripts (uses seedhash, openpyxl, python-docx) |
| `unsloth` | 3.12.9 | Fine-tune + inference |

`unsloth` env has: `unsloth 2025.11.1`, `transformers 4.57.1`, `peft 0.17.1`, `trl 0.23.0`, `bitsandbytes 0.48.2`, `accelerate 1.11.0`, `datasets 4.4.0`, `xformers 0.0.32.post2`, `torch 2.8.0+cu126`, `tiktoken 0.13.0`, `seedhash 0.1.0`.

### LLM-task selection (Leo)

After scouting `.code_base/notebooks/`, Leo picked **SFT-LoRA on Qwen3-4B-Instruct, full train split, completion-only loss masking** as the first task. Cost ≈ $4.50 for all 5 seeds on an A100; ~35-60 min/seed locally. Alternatives ranked: SFT→GRPO on worked-Apply subset (deferred); BERT MC-letter classifier (baseline only).

### Training notebook

`models/recipes/qwen3_4b_seed00_bf16_lora.ipynb` — 31 cells. bf16-LoRA (not QLoRA), r=16/α=32, 3 epochs cosine LR + 5% warmup, EarlyStopping(patience=3), `train_on_responses_only` masking, post-training eval on test split with type/Bloom/chapter accuracy breakdown.

### Windows-specific adjustments

- **vLLM 0.21.0 removed** from the unsloth env. The Windows wheel installs Python files but no native `vllm._C` extension. `unsloth_zoo/vllm_utils.py:91-152` blindly imports vllm submodules when `find_spec("vllm")` says truthy → `ModuleNotFoundError` cascades into `import unsloth`. Uninstalling vllm cleanly skips the patching block.
- `HF_HOME=D:\hf_cache` so the ~4 GB base download goes to the larger-free-space drive.
- `dataloader_num_workers=0` for Windows + Jupyter safety (spawn re-imports the notebook module).
- Serving path swapped from vLLM to **Unsloth-native inference / GGUF + llama.cpp + Ollama**. Optional GGUF export cell added to the notebook.
- Hard assert in §1 of the notebook fails fast if vllm is re-installed (with the exact uninstall command in the error message).

### `.meta/` directory introduced

- `hardware.md` moved here.
- This devlog created.
- Pat-pm will produce `ROADMAP.md` (version numbers, priorities, hardware-driven algorithm notes).

---

_Next entry below this line. Keep newest-on-top per phase; each phase H2-dated._
