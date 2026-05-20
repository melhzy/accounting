# Accounting LLM Framework — ROADMAP

_Pat-arbiter synthesis. Read at the start of every session. Source: `.meta/host.json` + `.meta/hardware.md` + `.meta/devlog.md`. Pinned today._

## Section 0 — Session-start host check (run first)

The repo is portable across **Windows / macOS (Intel + Apple Silicon) / Linux**. Each OS forces different algorithm defaults (see §4). At the start of every session:

```bash
python .meta/probe_host.py
```

This regenerates `.meta/host.json` (machine-readable). Pat compares it to `.meta/hardware.md`:

- **OS family changed** (e.g. Windows → macOS) → HARD WARNING; §4 algorithm constraints stale; ROADMAP must be refreshed before training.
- **CPU arch family changed** (e.g. `x86_64` → `arm64`) → ML wheel set may be incompatible; bitsandbytes / flash-attn likely unavailable; QLoRA fallback path is gone. Re-derive §4 entirely.
- **Bitness mismatch** (`os.arch.bits=64` but `python_bits=32`, or 32-bit OS) → hard FAIL. No supported ML stack. Stop and prompt the user to fix the Python install before any training.
- **CPU vendor changed** (Intel ↔ AMD ↔ Apple) → soft warning; kernel selection (MKL vs OpenBLAS vs Accelerate) may change but generally non-blocking on `x86_64`.
- **GPU model changed** (e.g. RTX 4090 Laptop → desktop A100 → Apple M3 Max) → VRAM accounting stale; recompute bf16-LoRA vs QLoRA verdict.
- **Critical ML package toggled** (vLLM installed/uninstalled, unsloth missing) → re-derive serving stack.

Last-known host (as of pin): **Linux Ubuntu 24.04 / `arm64` (aarch64) 64-bit / Python 3.13.11 64-bit (conda base) / NVIDIA GB10 Grace-Blackwell (sm_120, compute_cap 12.1, driver 580.95.05) / 119.6 GB unified LPDDR5X / 2,210 GB free at repo root.** Probed 2026-05-20. The previous Windows / x86_64 / RTX 4090 Laptop sm_89 / Python 3.12.9 `unsloth` env / 64 GB RAM / `D:` host is RETIRED — every HARD WARNING in this section fires (OS family, CPU arch family, GPU model, critical ML packages all changed). `.meta/hardware.md` and ROADMAP §2 "Hardware profile" row + §4 algorithm constraints are STALE pending Leo's rewrite. The ML stack on the new host is empty (`psutil` only) — no torch, transformers, peft, trl, unsloth, bitsandbytes, accelerate, datasets, or vllm. Eval data + ETL artifacts survived the move: `eval/spiceland9e.jsonl` sha256 still matches the `spiceland9e-v1.0.0` anchor `95f1ae448c693088…`; all 5 seed splits intact per `eval/sft/splits/manifest.json`.

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
- **Current pin**: no production adapter yet. Next run id: **`qwen3-4b-4bit-qlora-s00-r0`** (per §4 forward statement — re-derived from the retired `bf16-lora` framing to match the DGX Spark playbook's 4-bit QLoRA path; seed manifest, dataset sha, holdout split id, and rank/alpha/modules carry over unchanged). The retired bf16 notebook is at `models/recipes/qwen3_4b_seed00_bf16_lora.ipynb`; container-aware DGX Spark recipe pending per Leo's option-(c) `models/recipes/dgx_spark/` template proposal.

## Section 2 — Progress snapshot

Ranked by user-trust impact. Verdict per surface.

| Surface | Status | Why |
|---|---|---|
| **Data (Diana)** | **PASS** | 4,453 canonical records, schema stable, all 5 data-extras met: schema preserved, noise rules applied, idempotent (sha256 stable), per-chapter stats logged in `eval/stats/`, `source_workbook`+`source_row` on every record. |
| **Splits (Diana + Leo)** | **PASS** | 5 seeds × scenario-grouped Bloom-stratified 80/10/10; cross-split scenario overlap = 0 in every seed; seeds derived from `seedhash` of a pinned input string. |
| **Pipeline (Diana)** | **PASS** | Three-stage idempotent. `_format.py` extracted, single-split path deleted, no dead code. README is current. |
| **Hardware profile (Leo)** | **PASS-refreshed** | Rewritten for DGX Spark / GB10 / aarch64 Ubuntu 24.04 / 119.6 GB UMA; substrate-of-record is the NVIDIA DGX Spark Unsloth playbook (NGC `nvcr.io/nvidia/pytorch:25.11-py3` + `pip install --no-deps unsloth unsloth_zoo bitsandbytes`); see `.meta/hardware.md`. |
| **Training recipe (Leo)** | **HOLD** | Notebook is wired and config-pinned, but **no training run has executed yet**. No `models/runs/`, no adapter sha, no `test_metrics.json`. Until r0 runs, every downstream claim is theoretical. |
| **Eval harness (Vera)** | **HOLD** | Post-training accuracy by type / Bloom / chapter is computed *inside the notebook* on the test split. A standalone `eval/run.py --baseline` does not exist; without it, there is no slice-table delta tooling for the post-implementation checklist. |
| **Agent roster (Pat)** | **PASS** | 8 lenses defined, Leo's scope demarcation from Solomon/Riley is clean, this ROADMAP closes the loop. |
| **Retrieval / RAG (Riley)** | **FAIL-by-omission, accepted** | GAAP Data corpus (~130 PDFs, 679 MB) deferred. Scoped out of SFT phase. Not blocking r0. |
| **Solver / tools (Solomon)** | **FAIL-by-omission, accepted** | No solver loop yet; the SFT adapter is the substrate it will eventually run on. Not blocking r0. |
| **Documentation (Pat)** | **PASS** | `eval/README.md`, `.meta/hardware.md`, `.meta/devlog.md` all current. This ROADMAP completes the meta layer. |

## Section 3 — Prioritized next steps

Ranked by user-trust impact. At most six.

1. **Launch `qwen3-4b-4bit-qlora-s00-r0` from a container-aware DGX Spark recipe.** Owner: Leo + user. Tradeoff: 4-bit QLoRA per the NVIDIA DGX Spark Unsloth playbook (chosen — playbook-validated path; ~25% Unsloth speedup auto-enabled; +14.3% per-batch on the Qwen3 family per `unsloth.ai/blog/nvidia-collab`) vs bf16-LoRA (no longer constrained by VRAM on 120 GB UMA but loses the playbook's prescribed-path safety + the validated `--no-deps` install chain). Effort: **S** (one container launch + smoke epoch). Gate: user picks notebook-recipe option (a/b/c) per Leo's recommendation.
2. **Extract notebook §12-§13 eval block into a reusable `eval/run.py`.** Owner: Vera. Tradeoff: extra abstraction cost now vs. unblocking every subsequent slice-table delta and the post-implementation checklist. Effort: **M**.
3. **Run seeds 01-04 to produce the variance estimate.** Owner: Leo. Tradeoff: 4× the wall-time (~3-4 hours) vs. a defensible mean±std on test accuracy that a single seed cannot give. Effort: **M** (sequential; the notebook is copy-and-flip-`SEED_DIR`).
4. **Add a Vera A/B harness that diffs `test_metrics.json` between two run ids.** Owner: Vera + Pat. Tradeoff: nontrivial to make slice-aware (>1pp regression flags), but without it every future model swap is unguarded. Effort: **M**.
5. **GGUF export + Ollama smoke-test for the s00-r0 adapter.** Owner: Leo. Tradeoff: q4_k_m loses ~1pp vs the bf16 base but produces a single-file portable artifact runnable on consumer hardware outside the DGX Spark NGC container (vLLM in-container remains the production batch-eval stack). Effort: **S** (recipe export cell, post-training).
6. **Riley scaffolding: chunk the GAAP Data PDFs into a retrieval index.** Owner: Riley. Tradeoff: starting RAG now competes for cycles with model evaluation; deferring leaves the solver loop ungrounded. Effort: **L**. Defer until #1-#4 are PASS.

## Section 4 — Hardware-driven algorithm constraints

Hardware dictates algorithm; every choice below is downstream of the probe at `.meta/host.json` + `.meta/hardware.md`. Substrate-of-record is the **NVIDIA DGX Spark Unsloth playbook** (`https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth`, last updated 2025-12-15) — every choice below comes out of that prescribed path.

- **Container as substrate (NGC `nvcr.io/nvidia/pytorch:25.11-py3`).** The NGC container ships PyTorch + CUDA 13.0 + sm_120 Triton kernels managed inside the image. Host aarch64 wheel resolution is bypassed entirely. **Forced default**: training and serving run *inside* the container, launched with `docker run --gpus all --ulimit memlock=-1 -it --ulimit stack=67108864 --entrypoint /usr/bin/bash --rm nvcr.io/nvidia/pytorch:25.11-py3`. The host conda base is read-only with respect to ML wheels and stays scoped to ETL.
- **Unsloth via `--no-deps` (load-bearing).** Inside the container, dependencies install as `pip install transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"` then `pip install --no-deps unsloth unsloth_zoo bitsandbytes`. The `--no-deps` flag is non-negotiable: container-managed PyTorch + Triton + CUDA 13.0 must NOT be overwritten by pip-resolved replacements; the wheels are version-managed by the container, NOT by pip-resolution. Any recipe that drops `--no-deps` is rejected on review. Unsloth's DGX Spark optimizations are auto-enabled on this device per `unsloth.ai/blog/nvidia-collab` (~25% speedup on top of the existing 2-5× vs HF Trainer; Qwen3-14B QLoRA SFT specifically validated +14.3% per-batch).
- **4-bit QLoRA is now first-class, not fallback.** Playbook-validated path is `FastModel.from_pretrained(model_name, max_seq_length=2048, load_in_4bit=True, load_in_8bit=False, full_finetuning=False)`. The earlier framing of "bf16-LoRA default, QLoRA as OOM-recovery" was a 4090 Laptop / sm_89 constraint and is **retired**. **Forced default**: 4-bit QLoRA via `FastModel.from_pretrained(load_in_4bit=True)` + `FastLanguageModel.get_peft_model` with rank 16, target modules `q,k,v,o,gate,up,down`, lora_alpha=16, lora_dropout=0, `use_gradient_checkpointing="unsloth"`, `optim="adamw_8bit"` (bitsandbytes 8-bit Adam). Playbook reference recipe is `unsloth/Phi-3.5-mini-instruct` with batch=2, grad_accum=4, max_seq_length=2048; ours scales analogously for Qwen3-4B and up.
- **119.6 GB UMA, sm_120 Blackwell, CUDA 13.0.** Unified Memory Architecture means CPU and GPU share the same 119.6 GB LPDDR5X pool — there is no separate "VRAM" budget. **Permits**: 4B-class LoRA/QLoRA (cheap), 8B-22B QLoRA (comfortable), and 4-bit 70B-class adapter fine-tunes (e.g. `Llama-3.3-70B-Instruct-bnb-4bit` from the playbook's supported pre-quantized list — was unreachable on the retired 16 GB VRAM host). **Rules out**: nothing in the SFT phase. The Unsloth double-buffer overhead is disclosed (+0.37 GB at 8B, +0.47 GB at 14B, +0.23 GB at 32B) and folded into the UMA accounting in `.meta/hardware.md`.
- **UMA OOM-recovery is a buffer-cache flush, not an OOM-kill.** Playbook-documented: `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`. This is the prescribed first response between back-to-back training launches — page-cache pressure from one side starves the other, but the flush gives the GPU back its share without changing the recipe. Do not reduce `max_seq_length` or batch as a first response to OOM; run the flush first.
- **bitsandbytes `adamw_8bit` validated on this host.** The playbook's `test_unsloth.py` exercises `SFTTrainer` from `trl==0.26.1` with `optim="adamw_8bit"` on Phi-3.5-mini. **Forced default**: optimizer is `adamw_8bit`; the 8-bit Adam state cuts optimizer footprint to ~0.1-0.5 GB on LoRA params, freeing UMA for activations.
- **Triton kernels via container CUDA 13.0 + sm_120.** The NGC container's recent Triton is sm_120-compatible; no host-side kernel work is required. Unsloth's existing Triton kernels (cross-entropy, RoPE, SwiGLU, fused norms) all light up. The earlier "partial sm_120 NF4 kernels" framing is **withdrawn** — the playbook validates the full path through `--no-deps` install of bitsandbytes against the container's CUDA 13.0 runtime.
- **vLLM serving is back on the menu via the container path.** The retired Windows host blocked vLLM because `vllm._C` was Linux-only and its absence broke `import unsloth` via `unsloth_zoo/vllm_utils.py:91-152`. On the DGX Spark inside the NGC container, vLLM installs natively on aarch64 Linux + sm_120. **Production batch-eval serving stack is vLLM** (continuous batching, paged KV cache); local-dev iteration uses `FastLanguageModel.for_inference(model)`; GGUF export to llama.cpp/Ollama remains the portable fallback. AWQ-4bit on vLLM remains the production quant path with the recovery-vs-fp16 score recorded on the 200-q probe per Leo's standing rule.
- **Python 3.13.11 host (conda base) vs container-managed Python.** Two-env split survives the platform move: host conda base drives ETL (`split_multi_seed.py`, `ingest_spiceland.py`, `extract_word_tables.py`); the container drives ML. The JSONL artifact at `eval/sft/splits/seed_*/...jsonl` remains the boundary — every cross-env handoff is mediated by sha256-pinned files, not Python objects. Eval data survived intact: `eval/spiceland9e.jsonl` sha256 still matches the `spiceland9e-v1.0.0` anchor `95f1ae448c693088…`; all 5 seed splits verified per `eval/sft/splits/manifest.json`.
- **Disk: 2,210 GB free at repo root.** Fits HF cache (~5 GB), 5-seed adapter checkpoints (~5 GB total at 4B; ~25 GB at 70B-class), training logs (~2 GB), GGUF exports (~2.5 GB × N quants), and a 70B-class 4-bit base download (~40 GB) with massive headroom. **Forced default**: adapter-only artifacts under `models/runs/<run_id>/` (gitignored); 4-bit base weights cached under a host-mounted `HF_HOME` so they survive container restarts.

**Forward statement**: The next algorithmic decision (whether to keep Qwen3-4B as the SFT pilot or upgrade the substrate to an 8B / 14B / 22B / 70B-class 4-bit base now that the UMA ceiling permits it) is no longer constrained by VRAM. It is constrained by Vera's slice-table delta and Leo's cost/latency probe — the substrate change must justify itself on accuracy and throughput, not on what fits. The pilot run `qwen3-4b-bf16-lora-s00-r0` should be re-derived as a **`qwen3-4b-4bit-qlora-s00-r0`** path inside the container (the bf16 framing was 4090-Laptop-driven; on DGX Spark the playbook-validated 4-bit QLoRA path is cheaper and faster) — but the seed manifest, dataset sha, holdout split id, and recipe rank/alpha/modules all carry over unchanged.

---

_Pinned versions today_: dataset `spiceland9e-v1.0.0` (sha256 `95f1ae448c693088…`) · pipeline `pipeline-v0.3.0` · next model run id `qwen3-4b-4bit-qlora-s00-r0` (not yet executed; substrate-of-record is the NVIDIA DGX Spark Unsloth playbook).

**Relevant paths**: `/home/zi/Documents/GitHub/accounting/eval/spiceland9e.jsonl` · `/home/zi/Documents/GitHub/accounting/eval/sft/splits/seed_00__351199285/` · `/home/zi/Documents/GitHub/accounting/models/recipes/qwen3_4b_seed00_bf16_lora.ipynb` (retired bf16 reference; DGX Spark recipe pending) · `/home/zi/Documents/GitHub/accounting/.meta/hardware.md` · `/home/zi/Documents/GitHub/accounting/.meta/devlog.md`.
