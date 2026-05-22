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

`models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb` — 31 cells. bf16-LoRA (not QLoRA), r=16/α=32, 3 epochs cosine LR + 5% warmup, EarlyStopping(patience=3), `train_on_responses_only` masking, post-training eval on test split with type/Bloom/chapter accuracy breakdown.

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

---

## 2026-05-20 (later) — Session 3 · Multi-host doctrine correction

**Context**: After pulling 8 commits from GitHub (DGX Spark substrate, r0 baseline, etc.), the agents-team's synthesis treated the host change (Windows → DGX Spark) as a **substrate replacement**: hardware.md was rewritten for DGX Spark only, ROADMAP §0 called the Windows host "RETIRED", and the bf16-LoRA Windows recipe got called "retired bf16 notebook" in §1 and "withdrawn" in §4.

**User correction**: "this repository should be compatible to all OS and CPU arch — Windows, macOS, and Linux with different kinds of hardware." The host change is a **switch of the ACTIVE pointer in a compatibility matrix**, not a retirement of the previous host.

**Fixed in this session**:

- **`.meta/hardware.md`** — added a compatibility-matrix table at the top with one row per supported host (★ ACTIVE = DGX Spark, `dormant` = Windows + RTX 4090 Laptop, `future` = macOS Apple Silicon / Linux x86_64 NVIDIA / Linux x86_64 AMD ROCm / Linux aarch64 non-DGX). Added a "Dormant host details — Windows + RTX 4090 Laptop" section that preserves the Windows row's prescribed path (bf16 LoRA, no vLLM, `dataloader_num_workers=0`, etc.). De-retired the inline language ("retired Windows host" → "Windows dormant row").
- **`.meta/ROADMAP.md`**:
  - **§0** rewritten to frame the host check as moving the ACTIVE pointer; never retiring previous hosts. Bullets sharpened: "switch §4 ACTIVE-row pointer", not "ROADMAP must be refreshed".
  - **§1 Model run versioning** — both `qwen3-4b-4bit-qlora-s00-r0` (DGX Spark ACTIVE row, executed) and `qwen3-4b-bf16-lora-s00-r0` (Windows dormant row, alive) are now listed as live targets that bind to the same seed_00 corpus and become directly comparable as a cross-row baseline.
  - **§4** restructured with explicit "★ ACTIVE — DGX Spark / dormant — Windows / future — macOS+Linux variants" matrix headers. The DGX Spark bullets are retained as the ACTIVE block; the Windows row gets a parallel dormant block. The "QLoRA fallback is gone", "earlier framing retired", "vLLM is back on the menu" framings replaced with "this row prescribes X; the dormant row prescribes Y".
  - **Forward statement** reframed: pilot runs on ACTIVE (DGX Spark, executed at 69.2%) and on dormant (Windows, recipe alive, not yet executed) bind to the same dataset sha + holdout, so they are a cross-row baseline once both run.
- **`.claude/agents/pat-pm.md`** — added a **Cardinal rule** to the session-start check section: "matrix, not substrate replacement". Forbidden phrasings ("X is retired", "§4 must be refreshed") and required phrasings ("ACTIVE pointer moved", "X is dormant, alive") spelled out. Steps 2-3 updated to explicitly mandate "switch the ★ ACTIVE pointer" and "add a new row" (never overwrite) when the OS/arch shifts.

**Lesson for the team**: the pat-pm.md doctrine already enumerated 6 platform combinations as a matrix, but the language "HARD WARNING → ROADMAP must be refreshed" nudged whoever synthesized the post-pull state to rewrite §4 for DGX Spark. The fix is at the language level — Pat now has explicit forbidden phrasings.

_Next entry below this line. Keep newest-on-top per phase; each phase H2-dated._

---

## 2026-05-21 — Session 4 · Claude Code harness layer + host drift

Two events this session.

**Harness layer (commit `a51d9c3`).** Shipped Anthropic's Claude Code harness blueprint, scoped to net-new value:
- `CLAUDE.md` (root) — lean pointers + project-wide critical gotchas; points at existing READMEs and `.claude/agents/` for layered context rather than duplicating them.
- `.claude/settings.json` — destructive-Bash deny (`rm -rf`, force-push, reset --hard, branch -D), build-artifact noise filters (cache dirs, Word lockfiles, adapter weights), `SessionStart` hook wiring (matchers: `startup`, `resume`).
- `.claude/hooks/session_start.py` — cross-platform stdlib hook (~130 LoC); auto-runs `probe_host.py`, then surfaces `[read first]` ROADMAP pointer, `[host]` current row summary, `[pins]` dataset / pipeline / run-id pins, `[lenses]` dispatch roster. ASCII-only output for Windows cp1252 stdout compatibility.
- `.gitignore` — `.claude/settings.local.json` (per-developer overrides, not checked in).

Deliberately not added: subdirectory `CLAUDE.md` files, skills, `HARNESS.md`, MCP servers, plugins. The existing per-directory READMEs + 8-lens agent system already satisfy the blog's "layered context" and "specialized expertise on demand" intents; duplicating them would be the bloat the blog explicitly warns about. Earlier in the session I created the redundant pieces speculatively, then walked them back after a candid review. Lesson for future harness work in this repo: **the agents/ + READMEs surface is the layered-context mechanism; harness work should reference it, not parallel it.** The commit also folded in 14 pre-staged DGX Spark layout renames that were in the index — bundled label is "Claude Code harness layer" but the commit description in `git show a51d9c3` lists both. Classifier blocked the `--amend` to expand the message.

**Host drift (Pat verdict).** The new `SessionStart` hook fired and regenerated `.meta/host.json`. The current host is Windows 11 + i9-13900HX + RTX 4090 Laptop sm_89 — the row that was `dormant` since 2026-05-20. Per the §0 protocol the ★ ACTIVE pointer in `.meta/hardware.md` matrix and ROADMAP §0/§4 moves to the Windows row; DGX Spark becomes `dormant`, alive. The executed `qwen3-4b-4bit-qlora-s00-r0` baseline (69.2% on the 464-row scorable test split) and `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` stay prescriptive for the moment a session runs on DGX Spark again — neither retired.

ROADMAP §3 reordered by ACTIVE-row actionability (Pat). Items now ranked: (1) extract notebook eval block into `eval/run.py` — Vera, cross-row; (2) execute `qwen3-4b-bf16-lora-s00-r0` on the Windows row — Leo + user, produces the cross-row baseline against the executed dormant-row r0; (3) GGUF export + Ollama smoke-test of the dormant-row adapter — Leo, cross-row applicable; (4) Vera A/B harness diffing `test_metrics.json`; (5) re-launch DGX Spark 4-bit QLoRA r1+ sweeps — deferred until that host is ACTIVE again; (6) seeds 01-04 variance — same defer condition.

**hardware.md restructure**: minimal-edit pass (preserved detail, flipped headers). The header (line 3) now reads "Probed 2026-05-21. ★ ACTIVE = Windows…"; matrix table ★ swapped; "Source-of-truth pointers per row" swapped; a new `## Dormant host details — NVIDIA DGX Spark` H2 introduces the previously-ACTIVE detail block; the previously-`Dormant host details — Windows + RTX 4090 Laptop` H2 was renamed to `## ★ ACTIVE host details — Windows + RTX 4090 Laptop`. The Bottom line H2 was relabeled to "DGX Spark (dormant) row". The DGX Spark detail blocks (Compute / Storage / Python environments / ML stack / Fine-tune feasibility / Launch / Serving) were left in place rather than physically swapped under the ACTIVE block — the matrix table + section headers carry the truth; physically swapping ~230 lines on every host switch is overkill and Pat's verdict explicitly said "swap ★ marker + headers", with content reordering listed as a nice-to-have not blocker.

**Post-implementation checklist (Pat, abbreviated)**: Eval-harness re-run N/A · Destructive gates PASS (settings.json deny list lands) · Observability N/A · Failure-mode handlers HOLD (verify `session_start.py` handles `probe_host.py` non-zero exit / missing host.json / JSON parse error — P2 follow-up, non-blocking) · Open follow-ups PASS-on-apply · Citation discipline N/A.

**Open follow-ups**:
- (P2) Verify `.claude/hooks/session_start.py` graceful degradation on probe failure paths.
- (P3) Once Vera ships `eval/run.py` (§3 #1), extend the hook to surface "last baseline slice-table" line.
- (P3) Confirm `.gitignore` rules still exclude adapter weights but keep `manifest.json` / `test_metrics.json` / `test_predictions.jsonl` in-repo under the new `models/runs/dgx_spark/...` host-nested path (the two-star pattern update in `.gitignore` is in working tree, not yet committed — will land with the next DGX Spark commit).

---

## 2026-05-22 — Session · DGX Spark recipe chain, seeding policy, v1.2.0 lens verdict

Session started 2026-05-21 on the ★ ACTIVE Windows row; bulk of decision-grade work landed 2026-05-22.

### Recipe chain — r1 + r2 prepared (Leo lens)

User asked for 5-10B thinking-model candidates from the Unsloth catalog. Filed by lineage, two stubs prepared targeting the dormant DGX Spark row (4-bit QLoRA path):

- **r1** at `models/recipes/dgx_spark/qwen3_8b_4bit_qlora_s00_r1.ipynb` — base model `unsloth/Qwen3-4B-Instruct-2507` → `unsloth/Qwen3-8B`. Variable isolated: **parameter count (4B→8B)**. Rendered with `enable_thinking=False` so the hybrid model's thinking prior is preserved for inference; the size ablation is clean against r0 (which was Instruct-2507, no thinking mode). Generated by `_build_r1_notebook.py` diff-patching r0; 18 labeled patches.
- **r2** at `models/recipes/dgx_spark/dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb` — base model `unsloth/Qwen3-8B` → `unsloth/DeepSeek-R1-0528-Qwen3-8B`. Variable isolated: **pretraining lineage (vanilla Qwen3 → R1-distilled reasoning)**. Same tokenizer, same backbone shape, same wall-time projection (~180-200 min from r0's measured 1.933 samples/s). Generated by `_build_r2_notebook.py` deriving from r1 (chain r0 → r1 → r2 gives one variable per hop).

Both recipes inherit r0's hyperparameters exactly (rank 16, alpha 32, target modules q/k/v/o/gate/up/down, batch 2 × accum 4 → effective 8, 3 epochs, cosine LR w/ 5% warmup, `adamw_8bit`, eval_steps 110, EarlyStopping patience 3). Builder pattern makes the diff auditable as a single file — re-runnable.

**Candidate ledger** added to `models/recipes/dgx_spark/README.md` enumerating 9 catalog entries with built/deferred/excluded decisions: DeepSeek-R1-Distill-Llama-3-8B (deferred — cross-family breaks the chain), DeepSeek-R1-Distill-Qwen-2.5-7B (deferred — older Qwen base), Ministral-3-8B-Reasoning (deferred — Mistral SP tokenizer), Qwen3-VL-8B-Thinking (excluded — multimodal), Phi-4-Mini/Reasoning (excluded — below/above the 5-10B band), Gemma-4-E4B (excluded — sub-5B at active-params). The doctrine: family-diversity probes belong in a separate chain rooted at their own r0-equivalent, not bolted onto this one.

**Post-r2 trajectory** sketched (not built) in the README: r3 = synthetic thinking traces from a teacher model (only way to actually *train* thinking behavior, not just preserve the inference-time capability); eval-side `_build_*_notebook.py` parameterization deferred until r1's manifest exists.

### Seeding policy — `eval/seeding.py` unified utility

User directed: "stick to seedhash (https://pypi.org/project/seedhash/); cover CPU + single GPU + multi-GPU one host + multi-GPU multi-host". Audited the repo first — `eval/split_multi_seed.py` already used `seedhash.SeedHashGenerator(SEEDHASH_INPUT).generate_seeds(N)` correctly (seed_00 → `seed_int=351199285`), but training-side seeding relied only on `SFTConfig(seed=...)` transitively through HF Trainer; no explicit cuDNN determinism flags, no `CUBLAS_WORKSPACE_CONFIG`, no per-rank derivation, no DataLoader worker_init_fn.

Shipped:

- **`eval/seeding.py`** (≈250 LoC) — single entrypoint `seed_everything(seed_int=… | seedhash_input=…, seed_index=…)`. Auto-detects topology via `torch.distributed.is_initialized()` falling back to `RANK`/`WORLD_SIZE`/`LOCAL_RANK`/`LOCAL_WORLD_SIZE` env vars (torchrun / accelerate launch / deepspeed) falling back to single-process defaults. Returns a `SeedingReport` dataclass with `.to_dict()` for manifest embedding. Strict mode is opt-in (`strict=True` → `torch.use_deterministic_algorithms(True, warn_only=True)` + cuDNN deterministic + benchmark=False + `CUBLAS_WORKSPACE_CONFIG=:4096:8`).
- **Per-rank seed derivation**: `derive_per_rank_seed(seedhash_input, seed_index, rank)` salts the input as `f"{seedhash_input}|seed_{seed_index:02d}|rank_{rank:04d}"` and runs a fresh `seedhash.SeedHashGenerator(salt).generate_seeds(1)[0]`. Deliberate choice over `seed_int + rank` arithmetic — keeps the derivation pure-`seedhash`, no collision risk on close seeds.
- **Framework-coupling scope** (documented explicitly after user asked): CPU layer + derivation are backend-agnostic; GPU layer is **tight to PyTorch + CUDA by design** (matches the substrate — Unsloth + transformers + peft + trl + bitsandbytes + vLLM all on torch); `transformers.set_seed` covers the HF Trainer code path. Each layer is independently skipped if its dep isn't importable. MLX (Apple Silicon `future` row), llama.cpp `llama_set_seed()`, and vLLM `SamplingParams(seed=...)` are deliberately NOT in scope — would need shims if those rows go ACTIVE; deferred-not-dropped.

Wired into: `eval/run.py` (new `--seed` and `--strict-determinism` flags; default seed read from the split's sibling `manifest.json`; `seeding_report` block added to `test_metrics.json`); `_build_r1_notebook.py` (§1 substrate cell now imports `seed_everything` and stores `SEEDING_REPORT`; §8 manifest dict carries `SEEDING_REPORT.to_dict()`); r2.ipynb inherits via the chain; `models/recipes/windows/_build_notebook.py` (§2 Configuration cell calls `seed_everything` before any torch CUDA op, then `seeding_report` lands in the bf16 manifest).

Did NOT touch the executed `qwen3-4b-4bit-qlora-s00-r0` notebook — frozen artifact; its manifest already carries `seed_int: 351199285` correctly, just without the explicit `seeding_report` block.

Smoke-tested on the Windows host: `python eval/seeding.py --rank 0` produces `seed_00: 351199285` matching the split manifest exactly; multi-host simulation via `RANK=2 WORLD_SIZE=4 LOCAL_WORLD_SIZE=2` correctly detects `multi_host` topology and derives `per_rank_seed=1049037614` ≠ rank-3's `841273176`.

Policy documented in `eval/README.md` (full section with layer-by-layer coupling table) and in user-memory at `seeding_policy.md`.

### SFT collapse diagnosis + lens fan-out (Diana + Carla + Edie + Pat)

User reported: r0's tuned model went answer-only (`**A**`, `**TRUE**`) while baseline `Qwen3-4B-Instruct-2507` did explain. Asked whether their fine-tune data was prepared wrong.

**Audited directly** instead of guessing. Profile of `eval/sft/splits/seed_00__351199285/train.jsonl` (3,538 rows):

- ~50% of assistant turns are ≤12 chars (just `**X**` / `**TRUE**` / single digit).
- Per-type explanation coverage: MC 49% · Essay/Problem 67% · **TF 0% · Matching 0.2%**.
- Canonical `eval/spiceland9e.jsonl` shows the same shape: **0.2% TF (1 of 426), 0.1% Matching (1 of 706)** have a non-empty `explanation` field.
- Ran Diana's `parse_word_metadata()` on `Spiceland9e_Chapter01_TB_AnswerKey.docx` directly: 146 question numbers extracted; only 14 (10%) have any `explanation_text` after `Answer:`. Q1-Q8 (TF) are just `Answer: TRUE` / `Answer: FALSE` with no rationale paragraphs. This is **publisher convention, not an ETL gap**.

Dispatched 3-lens fan-out (Diana + Carla + Edie) in parallel, Pat closed:

- **Diana**: PASS on the audit. No ETL fix possible. Ran the alt-phrasing regex catalog (`Rationale:` 0, `Reasoning:` 0, `Solution:` 0, `Feedback:` 0, `Discussion:` 0) across Ch.05/13/18 — only `Explanation:` ever appears in source. Excel `Explanation` column is 1/250 populated for TF, 0/532 for Matching across Ch.06-21.
- **Carla**: Synthesized rationales are ACCEPTABLE WITH DISCIPLINE. Six-item gate: teacher pin + provenance class field, citation regex-resolves against known-good ASC list, standards-version smell triggers (Diana's v1.1.0 catalog) wired as hard rejects, answer-consistency check (rationale concludes with gold; disagreement escalates to Pat, not auto-fixed), ≥5% CPA spot-review stratified by chapter, `synthetic_rationale: true` provenance tag so Vera can slice. TF defensible (bright-line rules), Matching defensible-but-narrower (definitional contrast).
- **Edie**: Sharp reframe — *"every type must have a rationale" is the right product goal but the wrong training-data gate.* The right gate is **"every SFT example must produce a coaching-capable output."** Recommends dropping rationale-less TF/Matching from SFT, keeping them in eval as graded-assessment surface only. Delivered Bloom × type rationale-shape table (citation-only at Remember; trap-naming at Apply+) and the grader-coach minimum (correct answer + standard + named misconception).
- **Pat synthesis**: Rank **A (filter `meta.has_worked_solution=True`) > B (synthesize w/ Carla's discipline) > D (hand-author top-up for top LOs) > C (loss weighting, stays deferred)**. Edie wins on the design gate; Leo wins on sequencing — v1.2.0 work does not start before r1 and r2 close, because r1 isolates the parameter-count variable and r2 isolates the reasoning-prior variable; if either fixes the collapse on its own, v1.2.0 is **cancelled**. Named tradeoff: A drops ~30% of training rows (4,453 → ~2,070 eligible); Vera must confirm MC-Remember and calculation slices don't regress >1pp.

### `spiceland9e-v1.2.0` plan queued

`.meta/v1_2_0_plan.md` written, mirroring `v1_1_0_plan.md` structure. §1 acceptance criteria (launch gate is "r1 + r2 executed and both still produce answer-only outputs"). §2 versioning event (MAJOR bump: filter flips a record's SFT inclusion). §3 Carla's six-item discipline list parked for option B if triggered. §4 Edie's Bloom × type rationale-shape table + grader-coach minimum. §5 post-implementation checklist (six LLM-touching + five data-touching extras). §6 launch gate Pat-owned, 4 steps, decision branch on r1/r2 deltas. Trigger phrasing: *"Pat, gate-check v1.2.0 against the r1/r2 deltas."*

ROADMAP §3 #5 updated with a "Queued post-r1+r2 (lens-verdict 2026-05-22)" sub-bullet pointing at the plan.

### Drift flag (Pat — surfacing, not fixing)

ROADMAP `.meta/ROADMAP.md` §1 line 43-44 and the §2 footer (line 135) still pin `spiceland9e-v1.0.0 / sha 95f1ae448c…`, but the SessionStart hook output, the executed r0 manifest, and the r0 notebook's §1 sha assert all agree on `spiceland9e-v1.1.0 / sha fed6eb17de8be1e4…`. Surface as a Pat-side refresh; not touched this session.

### Open follow-ups

- (P0, gated on user) Bring DGX Spark row ACTIVE and launch r1; once `models/runs/dgx_spark/qwen3-8b-4bit-qlora-s00-r1/manifest.json` lands, run r2 on top.
- (P1, conditional on r1+r2 outcomes) Activate `.meta/v1_2_0_plan.md` if both r1 and r2 still produce answer-only outputs.
- (P2) Pat refreshes ROADMAP §1 + §2 footer to v1.1.0 (drift flagged above).
- (P3) Eval-side `_build_eval_notebook.py` / `_build_judge_notebook.py` / `_build_two_stage_judge.py` currently hardcode `qwen3-4b-4bit-qlora-s00-r0` as `RUN_ID` (line 101 of the eval builder). Parameterize once r1 emits a manifest; premature to refactor before r1 outputs exist.
- (P3) MLX / llama.cpp `llama_set_seed()` / vLLM `SamplingParams(seed=...)` shims in `eval/seeding.py` — add only when the corresponding hardware row goes ACTIVE.
