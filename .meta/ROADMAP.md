# Accounting LLM Framework — ROADMAP

_Pat-arbiter synthesis. Read at the start of every session. Source: `.meta/host.json` + `.meta/hardware.md` + `.meta/devlog.md`. Pinned today._

## Section 0 — Session-start host check (run first)

The repo is portable across **Windows / macOS (Intel + Apple Silicon) / Linux on x86_64 or arm64**. §4 is a **compatibility matrix** — one row per supported host configuration. At the start of every session:

```bash
python .meta/probe_host.py
```

This regenerates `.meta/host.json` (machine-readable). Pat compares it to `.meta/hardware.md`'s matrix and identifies which row is **ACTIVE** for this session. **The ACTIVE pointer moves; previous rows stay as first-class supported targets — never retired.**

When the probe shows drift from the previously-ACTIVE row:

- **OS family changed** (e.g. Windows → Linux) → switch the ACTIVE-row pointer in §4 / `.meta/hardware.md` to the row matching the new OS. The previous row becomes `dormant`, not retired. If the new OS is not yet in the matrix, **add a new row** — do not overwrite an existing one.
- **CPU arch family changed** (e.g. `x86_64` → `arm64`) → same — switch the active pointer; preserve every other row. The ML wheel set on the new arch may differ (no bitsandbytes on Apple Silicon, etc.), but that is a property of the new row's prescribed path, not a reason to delete the old row.
- **Bitness mismatch** (`os.arch.bits=64` but `python_bits=32`, or 32-bit OS) → **hard FAIL** for THIS host. No row in the matrix supports 32-bit. Prompt the user to fix the Python install or move to a 64-bit host.
- **CPU vendor changed** (Intel ↔ AMD ↔ Apple at the same arch family) → soft warning; usually within the same row.
- **GPU model changed** within the same OS/arch (e.g. RTX 4090 Laptop → desktop A100) → may stay in the same matrix row but the VRAM accounting for that row needs updating.
- **Critical ML package toggled** (vLLM installed/uninstalled, unsloth missing) → re-derive serving stack for the ACTIVE row only.

**Last-active host (probed 2026-05-21)**: ★ Windows 11 + RTX 4090 Laptop · x86_64 (Intel i9-13900HX, 24c/32t) · NVIDIA RTX 4090 Laptop sm_89 · 16 GB VRAM / 64 GB DDR5-5600 · Python 3.13 (system) + conda `unsloth` env (Python 3.12.9, torch 2.8.0+cu126). This is row ★ ACTIVE in the §4 / hardware.md matrix.

**Last-active before this**: NVIDIA DGX Spark · Ubuntu 24.04 LTS aarch64 · ARM Neoverse V2 · NVIDIA GB10 Grace-Blackwell (sm_120, CUDA 13.0) · 119.6 GB UMA · Python 3.13.11 (host conda base) + NGC container `nvcr.io/nvidia/pytorch:25.11-py3` (probed 2026-05-20). Row is now `dormant`; the `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` recipe and the executed `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json` baseline (69.2% on the 464-row scorable test split) remain **alive** and prescriptive for any future session that runs on this host.

Eval data + ETL artifacts are platform-agnostic and survived the active-row switch intact: `eval/spiceland9e.jsonl` sha256 matches the `spiceland9e-v1.0.0` anchor `95f1ae448c693088…`; all 5 seed splits verified per `eval/sft/splits/manifest.json`.

---



## Section 1 — Versioning scheme

Three independent version tracks, semver-shaped. Bumps justified by what changed, never by elapsed time.

### Dataset version — `spiceland9e-vMAJOR.MINOR.PATCH`

- **MAJOR**: noise-rule semantics change (a rule added/removed/altered such that a record's gold answer or `meta.has_worked_solution` could flip).
- **MINOR**: source `.docx`/`.xlsx` content changes, or schema field added/renamed.
- **PATCH**: ETL refactor that should be byte-identical but isn't (line endings, sort, formatting).
- **Anchor**: sha256 of `eval/spiceland9e.jsonl` is the truth. Today: **`95f1ae448c693088…`**.
- **Current pin**: `spiceland9e-v1.0.0` (first stable corpus: 4,453 records, 10 noise rules applied, Word `Explanation:` recovery enabled, MC mislabel reclass active).

### Pipeline version — `pipeline-vMAJOR.MINOR.PATCH`

- Covers `eval/extract_word_tables.py`, `eval/ingest_spiceland.py`, `eval/split_multi_seed.py`, `eval/_format.py`.
- **MAJOR**: split contract changes (fractions, scenario-grouping rule, stratification key).
- **MINOR**: new optional output (e.g. a probe set, a streaming variant).
- **PATCH**: bug fix that does not change output sha256s.
- **Current pin**: `pipeline-v0.3.0` (three-stage idempotent ETL, scenario-grouped Bloom-stratified multi-seed 80/10/10, `_format.py` consolidated, single-split path retired).

### Model run versioning — `<family>-<size>-<precision>-<method>-s<NN>-r<R>`

- Example: `qwen3-4b-bf16-lora-s00-r0`. `s00` = seed_00 (seed_int 351199285). `r0` = first run; re-runs increment `r`.
- Each run produces `models/runs/<run_id>/manifest.json` recording: `base_model`, `tokenizer_revision`, `adapter_sha256`, the seed manifest's `source_jsonl_sha256` (binds the run to a dataset version), the recipe block, and metrics.
- **Current pin**: no production adapter yet. The model-run-id naming encodes precision + method so the **same seed can be trained on any active row's prescribed path** and the runs sit alongside each other in `models/runs/` without collision. Two live recipe targets:
  - On ★ ACTIVE row (DGX Spark): **`qwen3-4b-4bit-qlora-s00-r0`** — 4-bit QLoRA per the DGX Spark playbook. Recipe at `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` (already executed; metrics at `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json`).
  - On `dormant` row (Windows + RTX 4090 Laptop): **`qwen3-4b-bf16-lora-s00-r0`** — bf16 LoRA per the 16 GB VRAM Windows recipe. Recipe at `models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb` — **alive**, prescribed when the Windows host is ACTIVE. Different row, different precision, same seed_00 corpus.
  - Both runs bind to the same `source_jsonl_sha256` and the same `seed_int=351199285` holdout, which makes them directly comparable as a cross-row baseline (one of Vera's deliverables in §3).

## Section 2 — Progress snapshot

Ranked by user-trust impact. Verdict per surface.

| Surface | Status | Why |
|---|---|---|
| **Data (Diana)** | **PASS** | 4,453 canonical records, schema stable, all 5 data-extras met: schema preserved, noise rules applied, idempotent (sha256 stable), per-chapter stats logged in `eval/stats/`, `source_workbook`+`source_row` on every record. |
| **Splits (Diana + Leo)** | **PASS** | 5 seeds × scenario-grouped Bloom-stratified 80/10/10; cross-split scenario overlap = 0 in every seed; seeds derived from `seedhash` of a pinned input string. |
| **Pipeline (Diana)** | **PASS** | Three-stage idempotent. `_format.py` extracted, single-split path deleted, no dead code. README is current. |
| **Hardware profile (Leo)** | **PASS-refreshed** | ★ ACTIVE = Windows 11 + RTX 4090 Laptop (sm_89, 16 GB VRAM, 64 GB DDR5; prescribed: native Unsloth conda env + bf16-LoRA; serve via llama.cpp/Ollama; no vLLM on Windows). DGX Spark (GB10 / aarch64 / 119.6 GB UMA / NGC container + 4-bit QLoRA) is dormant; both rows alive. See `.meta/hardware.md` matrix. |
| **Training recipe (Leo)** | **MIXED** | ACTIVE-row target is `qwen3-4b-bf16-lora-s00-r0` on Windows — recipe alive at `models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb`, **not yet executed**, no `manifest.json` / `test_metrics.json` on this row. Dormant-row baseline `qwen3-4b-4bit-qlora-s00-r0` on DGX Spark **was executed** (69.2% on 464-row scorable test split; `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json`). |
| **Eval harness (Vera)** | **HOLD** | Post-training accuracy by type / Bloom / chapter is computed *inside the notebook* on the test split. A standalone `eval/run.py --baseline` does not exist; without it, there is no slice-table delta tooling for the post-implementation checklist. |
| **Harness layer (Pat)** | **PASS** | Commit `a51d9c3` shipped root `CLAUDE.md`, `.claude/settings.json` (destructive-Bash deny + noise filters + SessionStart hook wiring), and `.claude/hooks/session_start.py` (auto-runs `probe_host.py`; surfaces ROADMAP §0 + version pins + lens roster). Scoped to net-new value per the Anthropic blueprint; subdirectory CLAUDE.md / skills / MCP / plugins deliberately not added. Hook fired this session and regenerated `.meta/host.json` → triggered the §0 host-drift verdict. |
| **Agent roster (Pat)** | **PASS** | 8 lenses defined, Leo's scope demarcation from Solomon/Riley is clean, this ROADMAP closes the loop. |
| **Retrieval / RAG (Riley)** | **FAIL-by-omission, accepted** | GAAP Data corpus (~130 PDFs, 679 MB) deferred. Scoped out of SFT phase. Not blocking r0. |
| **Solver / tools (Solomon)** | **FAIL-by-omission, accepted** | No solver loop yet; the SFT adapter is the substrate it will eventually run on. Not blocking r0. |
| **Documentation (Pat)** | **PASS** | `eval/README.md`, `.meta/hardware.md`, `.meta/devlog.md` all current. This ROADMAP completes the meta layer. |

## Section 3 — Prioritized next steps

Ranked by user-trust impact. At most six.

Reordered 2026-05-21 by ACTIVE-row actionability (Pat). ACTIVE = Windows. Items 1-4 are workable on the current host; items 5-6 are DGX-Spark-substrate and are explicitly **deferred-not-dropped** until that host is ACTIVE again.

1. **Extract notebook eval block into a reusable `eval/run.py`.** Owner: Vera. Cross-row work (pure Python over JSONL + per-seed manifest). Tradeoff: extra abstraction cost now vs. unblocking every subsequent slice-table delta and the post-implementation checklist; turns the executed dormant-row `qwen3-4b-4bit-qlora-s00-r0` baseline into a re-scoreable artifact instead of a single notebook output. Effort: **M**. ACTIVE-row actionable now.
2. **Execute `qwen3-4b-bf16-lora-s00-r0` on the ACTIVE Windows row.** Owner: Leo + user. Tradeoff: bf16 LoRA via `models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb` (the row's prescribed path, ~50-70 min/epoch on 16 GB VRAM, no QLoRA dependency) vs waiting for the next DGX Spark session to run there. Produces the cross-row baseline against the dormant-row r0 (both bind to `source_jsonl_sha256` + `seed_int=351199285`, directly comparable per the §1 model-run-id naming). Effort: **S** (single seed). Gate: user opens the existing recipe and runs all cells.
3. **GGUF export + Ollama smoke-test for the dormant-row `qwen3-4b-4bit-qlora-s00-r0` adapter.** Owner: Leo. Cross-row applicable — the adapter file is platform-agnostic; llama.cpp / Ollama are the ACTIVE Windows row's serving stack anyway. Tradeoff: q4_k_m loses ~1pp vs the bf16 base but produces a portable single-file artifact runnable outside the DGX Spark NGC container. Effort: **S**. ACTIVE-row actionable now.
4. **Add a Vera A/B harness diffing `test_metrics.json` between two run ids.** Owner: Vera + Pat. Tradeoff: nontrivial to make slice-aware (>1pp regression flags), but without it every future model swap is unguarded. Becomes higher-leverage once item #2 produces the Windows bf16 baseline to diff against the dormant-row DGX Spark r0. Effort: **M**. ACTIVE-row actionable; blocks on #1 for the run.py substrate.
5. **(Deferred — needs DGX Spark ACTIVE) Re-launch the 4-bit QLoRA recipe on the DGX Spark row.** Owner: Leo + user. The executed `qwen3-4b-4bit-qlora-s00-r0` baseline (69.2%) is in-repo; further DGX Spark r-bumps (r1, r2 — recipe sweeps, longer training, alternative bases) wait for that host. Effort: **S** per run.
6. **(Deferred — needs DGX Spark ACTIVE) Seeds 01-04 variance run.** Owner: Leo. 4× the wall-time per row. Could be partially executed on ACTIVE Windows row as a parallel bf16-LoRA variance estimate; the DGX Spark 4-bit QLoRA variance estimate waits for that host. Effort: **M** (sequential).

## Section 4 — Hardware-driven algorithm constraints (compatibility matrix)

Hardware dictates algorithm. This section is a **matrix**: one block per supported host configuration. The ★ ACTIVE block is the prescribed path for the current session (set by Pat's host check in §0). `dormant` blocks remain alive — they apply the moment a session runs on that host again. **Never retire a block; never delete it for being inactive.**

The matrix below shows the prescribed path per row. The ★ ACTIVE block is detailed first; `dormant` and `future` blocks reference the recipe/notebook that targets them.

### ★ ACTIVE — NVIDIA DGX Spark / Ubuntu 24.04 aarch64 / GB10 sm_120 / 119.6 GB UMA

Substrate-of-record is the **NVIDIA DGX Spark Unsloth playbook** (`https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth`, last updated 2025-12-15). Every constraint in this block comes out of that prescribed path.

- **Container as substrate (NGC `nvcr.io/nvidia/pytorch:25.11-py3`).** The NGC container ships PyTorch + CUDA 13.0 + sm_120 Triton kernels managed inside the image. Host aarch64 wheel resolution is bypassed entirely. **Forced default**: training and serving run *inside* the container, launched with `docker run --gpus all --ulimit memlock=-1 -it --ulimit stack=67108864 --entrypoint /usr/bin/bash --rm nvcr.io/nvidia/pytorch:25.11-py3`. The host conda base is read-only with respect to ML wheels and stays scoped to ETL.
- **Unsloth via `--no-deps` (load-bearing).** Inside the container, dependencies install as `pip install transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"` then `pip install --no-deps unsloth unsloth_zoo bitsandbytes`. The `--no-deps` flag is non-negotiable: container-managed PyTorch + Triton + CUDA 13.0 must NOT be overwritten by pip-resolved replacements; the wheels are version-managed by the container, NOT by pip-resolution. Any recipe that drops `--no-deps` is rejected on review. Unsloth's DGX Spark optimizations are auto-enabled on this device per `unsloth.ai/blog/nvidia-collab` (~25% speedup on top of the existing 2-5× vs HF Trainer; Qwen3-14B QLoRA SFT specifically validated +14.3% per-batch).
- **4-bit QLoRA is first-class on this row.** Playbook-validated path is `FastModel.from_pretrained(model_name, max_seq_length=2048, load_in_4bit=True, load_in_8bit=False, full_finetuning=False)`. The "bf16-LoRA default, QLoRA as OOM-recovery" framing belongs to the **dormant Windows / 4090 Laptop / sm_89 row** (16 GB VRAM forces bf16 as the practical default there); it remains the prescribed path on that row. On this ACTIVE row, **forced default**: 4-bit QLoRA via `FastModel.from_pretrained(load_in_4bit=True)` + `FastLanguageModel.get_peft_model` with rank 16, target modules `q,k,v,o,gate,up,down`, lora_alpha=16, lora_dropout=0, `use_gradient_checkpointing="unsloth"`, `optim="adamw_8bit"` (bitsandbytes 8-bit Adam). Playbook reference recipe is `unsloth/Phi-3.5-mini-instruct` with batch=2, grad_accum=4, max_seq_length=2048; ours scales analogously for Qwen3-4B and up.
- **119.6 GB UMA, sm_120 Blackwell, CUDA 13.0.** Unified Memory Architecture means CPU and GPU share the same 119.6 GB LPDDR5X pool — there is no separate "VRAM" budget. **Permits**: 4B-class LoRA/QLoRA (cheap), 8B-22B QLoRA (comfortable), and 4-bit 70B-class adapter fine-tunes (e.g. `Llama-3.3-70B-Instruct-bnb-4bit` from the playbook's supported pre-quantized list — unreachable on the dormant Windows row's 16 GB VRAM ceiling but comfortable here). **Rules out**: nothing in the SFT phase. The Unsloth double-buffer overhead is disclosed (+0.37 GB at 8B, +0.47 GB at 14B, +0.23 GB at 32B) and folded into the UMA accounting in `.meta/hardware.md`.
- **UMA OOM-recovery is a buffer-cache flush, not an OOM-kill.** Playbook-documented: `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`. This is the prescribed first response between back-to-back training launches — page-cache pressure from one side starves the other, but the flush gives the GPU back its share without changing the recipe. Do not reduce `max_seq_length` or batch as a first response to OOM; run the flush first.
- **bitsandbytes `adamw_8bit` validated on this host.** The playbook's `test_unsloth.py` exercises `SFTTrainer` from `trl==0.26.1` with `optim="adamw_8bit"` on Phi-3.5-mini. **Forced default**: optimizer is `adamw_8bit`; the 8-bit Adam state cuts optimizer footprint to ~0.1-0.5 GB on LoRA params, freeing UMA for activations.
- **Triton kernels via container CUDA 13.0 + sm_120.** The NGC container's recent Triton is sm_120-compatible; no host-side kernel work is required. Unsloth's existing Triton kernels (cross-entropy, RoPE, SwiGLU, fused norms) all light up. (The dormant Windows row's "partial sm_120 NF4 kernels" concern was sm_89-specific and does not apply here; on this row, the playbook validates the full path through `--no-deps` install of bitsandbytes against the container's CUDA 13.0 runtime.)
- **vLLM serving works on this row.** vLLM installs natively on aarch64 Linux + sm_120 inside the NGC container. **Production batch-eval serving stack is vLLM** (continuous batching, paged KV cache); local-dev iteration uses `FastLanguageModel.for_inference(model)`; GGUF export to llama.cpp/Ollama remains the portable fallback. AWQ-4bit on vLLM is the production quant path with the recovery-vs-fp16 score recorded on the 200-q probe per Leo's standing rule. (Contrast with the dormant Windows row, where `vllm._C` is unavailable — `unsloth_zoo/vllm_utils.py:91-152` then breaks `import unsloth`; on that row the serving stack is Unsloth-native + llama.cpp/Ollama only.)
- **Python 3.13.11 host (conda base) vs container-managed Python.** Two-env split survives the platform move: host conda base drives ETL (`split_multi_seed.py`, `ingest_spiceland.py`, `extract_word_tables.py`); the container drives ML. The JSONL artifact at `eval/sft/splits/seed_*/...jsonl` remains the boundary — every cross-env handoff is mediated by sha256-pinned files, not Python objects. Eval data survived intact: `eval/spiceland9e.jsonl` sha256 still matches the `spiceland9e-v1.0.0` anchor `95f1ae448c693088…`; all 5 seed splits verified per `eval/sft/splits/manifest.json`.
- **Disk: 2,210 GB free at repo root.** Fits HF cache (~5 GB), 5-seed adapter checkpoints (~5 GB total at 4B; ~25 GB at 70B-class), training logs (~2 GB), GGUF exports (~2.5 GB × N quants), and a 70B-class 4-bit base download (~40 GB) with massive headroom. **Forced default**: adapter-only artifacts under `models/runs/<run_id>/` (gitignored); 4-bit base weights cached under a host-mounted `HF_HOME` so they survive container restarts.

### dormant — Windows + RTX 4090 Laptop (x86_64, sm_89, 16 GB VRAM)

Prescribed path when this row becomes ACTIVE: native Windows + `unsloth` conda env (Python 3.12.9) + bf16 LoRA at `r=16, batch=2, seq=2048, grad_accum=8` + Unsloth-native / llama.cpp serving. **vLLM is NOT available** on Windows (`vllm._C` is Linux-only; presence breaks `import unsloth` via `unsloth_zoo/vllm_utils.py:91-152`). DataLoader `num_workers=0` (Windows spawn). `HF_HOME=D:\hf_cache`. QLoRA held as OOM-recovery fallback only — bf16 is the default because the 16 GB VRAM ceiling is real but workable for 4B-class with gradient checkpointing.

Recipe: `models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb` — alive and prescriptive when this row is ACTIVE.

### future — macOS Apple Silicon · Linux x86_64+NVIDIA · Linux x86_64+AMD-ROCm · Linux aarch64 (non-DGX)

Stubbed in `.meta/hardware.md` "Future host details — templates" section. When `probe_host.py` runs on one of these hosts for the first time, populate the row's prescribed path and flip `future` → `★ ACTIVE` while the previous ★ becomes `dormant`.

---

**Forward statement**: With the ACTIVE pointer now on the Windows row, the next algorithmic decision is **executing the bf16-LoRA pilot `qwen3-4b-bf16-lora-s00-r0`** to produce the cross-row baseline against the already-executed dormant-row 4-bit-QLoRA `qwen3-4b-4bit-qlora-s00-r0` (69.2% on the 464-row scorable test split). Both runs bind to the same `source_jsonl_sha256` and the same seed_00 holdout, making them directly comparable. The substrate-vs-base-model question (4B vs 8B/14B/22B/70B) reopens when DGX Spark is ACTIVE again — that's where the 119.6 GB UMA ceiling makes 70B-class 4-bit fine-tuning reachable; the Windows row's 16 GB VRAM caps that ambition at 4B-class for now.

---

_Pinned versions today_: dataset `spiceland9e-v1.0.0` (sha256 `95f1ae448c693088…`) · pipeline `pipeline-v0.3.0` · ACTIVE-row run id `qwen3-4b-bf16-lora-s00-r0` (Windows, recipe alive at `models/recipes/windows/qwen3_4b_seed00_bf16_lora.ipynb`, not yet executed) · dormant-row run id `qwen3-4b-4bit-qlora-s00-r0` (DGX Spark, executed; metrics at `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json`, 69.2%).

**Relevant paths** (ACTIVE row, Windows): `D:\Github\accounting\eval\spiceland9e.jsonl` · `D:\Github\accounting\eval\sft\splits\seed_00__351199285\` · `D:\Github\accounting\models\recipes\windows\qwen3_4b_seed00_bf16_lora.ipynb` · `D:\Github\accounting\.meta\hardware.md` · `D:\Github\accounting\.meta\devlog.md`.

**Relevant paths** (dormant row, DGX Spark): `~/Documents/GitHub/accounting/models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` — alive; metrics at `~/Documents/GitHub/accounting/models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json` (executed, 69.2%).
