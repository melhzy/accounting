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

Last-known host (as of pin): **Windows 11 / `x86_64` 64-bit Intel / Python 3.12.9 64-bit (unsloth env) / RTX 4090 Laptop 16 GB / 64 GB RAM / `D:` 167 GB free.**

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
- **Current pin**: no production adapter yet. Next run id: **`qwen3-4b-bf16-lora-s00-r0`** (notebook ready at `D:\Github\accounting\models\recipes\qwen3_4b_seed00_bf16_lora.ipynb`).

## Section 2 — Progress snapshot

Ranked by user-trust impact. Verdict per surface.

| Surface | Status | Why |
|---|---|---|
| **Data (Diana)** | **PASS** | 4,453 canonical records, schema stable, all 5 data-extras met: schema preserved, noise rules applied, idempotent (sha256 stable), per-chapter stats logged in `eval/stats/`, `source_workbook`+`source_row` on every record. |
| **Splits (Diana + Leo)** | **PASS** | 5 seeds × scenario-grouped Bloom-stratified 80/10/10; cross-split scenario overlap = 0 in every seed; seeds derived from `seedhash` of a pinned input string. |
| **Pipeline (Diana)** | **PASS** | Three-stage idempotent. `_format.py` extracted, single-split path deleted, no dead code. README is current. |
| **Hardware profile (Leo)** | **PASS** | Probed, documented at `.meta/hardware.md`. bf16-LoRA budget computed at ~16 GB on the 4090 Laptop; QLoRA fallback identified. |
| **Training recipe (Leo)** | **HOLD** | Notebook is wired and config-pinned, but **no training run has executed yet**. No `models/runs/`, no adapter sha, no `test_metrics.json`. Until r0 runs, every downstream claim is theoretical. |
| **Eval harness (Vera)** | **HOLD** | Post-training accuracy by type / Bloom / chapter is computed *inside the notebook* on the test split. A standalone `eval/run.py --baseline` does not exist; without it, there is no slice-table delta tooling for the post-implementation checklist. |
| **Agent roster (Pat)** | **PASS** | 8 lenses defined, Leo's scope demarcation from Solomon/Riley is clean, this ROADMAP closes the loop. |
| **Retrieval / RAG (Riley)** | **FAIL-by-omission, accepted** | GAAP Data corpus (~130 PDFs, 679 MB) deferred. Scoped out of SFT phase. Not blocking r0. |
| **Solver / tools (Solomon)** | **FAIL-by-omission, accepted** | No solver loop yet; the SFT adapter is the substrate it will eventually run on. Not blocking r0. |
| **Documentation (Pat)** | **PASS** | `eval/README.md`, `.meta/hardware.md`, `.meta/devlog.md` all current. This ROADMAP completes the meta layer. |

## Section 3 — Prioritized next steps

Ranked by user-trust impact. At most six.

1. **Launch `qwen3-4b-bf16-lora-s00-r0` from the notebook.** Owner: Leo + user. Tradeoff: bf16-LoRA (chosen — ~16 GB tight but headroom of ~2.2 GB) vs QLoRA (would free ~6 GB but introduces NF4 quantization noise into the gradient). Effort: **S** (one notebook run, ~35–60 min).
2. **Extract notebook §12-§13 eval block into a reusable `eval/run.py`.** Owner: Vera. Tradeoff: extra abstraction cost now vs. unblocking every subsequent slice-table delta and the post-implementation checklist. Effort: **M**.
3. **Run seeds 01-04 to produce the variance estimate.** Owner: Leo. Tradeoff: 4× the wall-time (~3-4 hours) vs. a defensible mean±std on test accuracy that a single seed cannot give. Effort: **M** (sequential; the notebook is copy-and-flip-`SEED_DIR`).
4. **Add a Vera A/B harness that diffs `test_metrics.json` between two run ids.** Owner: Vera + Pat. Tradeoff: nontrivial to make slice-aware (>1pp regression flags), but without it every future model swap is unguarded. Effort: **M**.
5. **GGUF export + Ollama smoke-test for the s00-r0 adapter.** Owner: Leo. Tradeoff: q4_k_m loses ~1pp vs bf16 but enables a serving path that actually runs on this Windows box. Effort: **S** (notebook §13, flip the guard).
6. **Riley scaffolding: chunk the GAAP Data PDFs into a retrieval index.** Owner: Riley. Tradeoff: starting RAG now competes for cycles with model evaluation; deferring leaves the solver loop ungrounded. Effort: **L**. Defer until #1-#4 are PASS.

## Section 4 — Hardware-driven algorithm constraints

Hardware dictates algorithm; every choice below is downstream of the probe at `.meta/host.json` + `.meta/hardware.md`.

- **CPU arch + bitness (current: `x86_64 64-bit`, Intel).** The framework's ML stack assumes 64-bit. **Algorithm impact by arch family**:
  - **`x86_64` Intel/AMD** (current) — full stack: `bitsandbytes` NF4/INT8, `flash-attn`, AVX2/AVX-512 GEMM. Windows `AMD64` and Linux `x86_64` are the same ISA; macOS Intel is too but with weaker GPU options.
  - **`arm64` Apple Silicon** — **no `bitsandbytes`** (no NF4/INT8 quant path), **no `flash-attn`** (CUDA-only); use `torch.backends.mps` instead of `torch.cuda`; unified memory means RAM = effective VRAM. Forced fallback: bf16 LoRA only (no QLoRA), llama.cpp GGUF for serving.
  - **`arm64` Linux** (Graviton, Ampere Altra, Raspberry Pi 5) — partial: bitsandbytes via community ARM build, flash-attn unavailable, PyTorch ARM wheels OK. Niche but possible.
  - **`x86` 32-bit** or **32-bit Python on 64-bit OS** — **ruled out**. No modern ML wheel set supports 32-bit. Probe flags this as a hard FAIL.
  Vendor matters less than arch but does shape kernel selection (Intel MKL vs OpenBLAS; AMD's `aocl` build of bitsandbytes). The probe records `cpu.vendor` so Pat can flag this when Intel-specific assumptions (e.g., MKL-backed numpy) leak into the code path.
- **16 GB VRAM (RTX 4090 Laptop, sm_89 Ada).** bf16-LoRA at `batch=2, seq=2048, grad_accum=8` lands at ~16 GB with ~2.2 GB headroom (per Leo's accounting in `.meta/hardware.md` §"VRAM accounting"). **Rules out**: any 7B+ model in bf16, full fine-tuning at any size, batch >2 at seq 2048, simultaneous training+inference. **Permits**: 4B-class LoRA/QLoRA, AWQ-4bit serving via llama.cpp/Ollama, FP8 experiments later (Ada supports it natively). **Forced default**: rank 16 LoRA on `q,k,v,o,gate,up,down` projections; gradient checkpointing `"unsloth"` ON; `adamw_8bit` optimizer.
- **No vLLM on Windows.** The wheel installs but `vllm._C` is Linux-only; presence of the package breaks `import unsloth` via `unsloth_zoo/vllm_utils.py:91-152`. **Algorithmic impact**: cannot use vLLM's continuous batching for batch eval, so eval generation goes through HF `model.generate()` per-record (~5-10× slower for a full test split). **Forced default**: serving stack is Unsloth-native or llama.cpp/Ollama on GGUF export. WSL-vLLM is a fallback path, not the default.
- **Python 3.13.3 (system) vs 3.12.9 (`unsloth` env).** Two-env split is non-negotiable (Unsloth's wheel constellation lags 3.13). **Algorithmic impact**: the data pipeline and the trainer cannot share in-memory state. The JSONL artifact at `eval/sft/splits/seed_*/...jsonl` is the boundary — every cross-env handoff is mediated by sha256-pinned files, not Python objects.
- **Disk: 167 GB free on `D:`.** Fits HF cache (~3 GB), 5 seeds × Qwen3-4B adapter checkpoints (~5 GB total), training logs (~2 GB), optional GGUF export (~2.5 GB × N quants). **Upper bound**: a 14B-class model or a full fine-tune (+optimizer state in fp32) blows this. **Forced default**: stay at 4B-class adapter-only artifacts until the disk constraint relaxes; do not check in checkpoints — they live under `models/runs/` (gitignored).
- **Windows OS.** Spawn (not fork) for multiprocess; PyTorch DataLoader workers re-import the notebook module in Jupyter and choke. No `os.sched_yield`, no Linux-only flash-attn Triton paths in some configurations, Triton emits non-fatal `cuobjdump.exe`/`nvdisasm.exe` warnings. **Forced default**: `dataloader_num_workers=0`, `HF_HOME=D:\hf_cache` set *before* importing transformers, and a hard assert in §1 of every training notebook that vllm is uninstalled.

**Forward statement**: The next algorithmic decision (whether to swap from bf16-LoRA to QLoRA for seeds 01-04) is constrained by the 16 GB VRAM ceiling of the 4090 Laptop AND the `x86_64` arch assumption (QLoRA depends on `bitsandbytes` which has no `arm64` wheel). The framework should default to bf16-LoRA at `r=16, batch=2, seq=2048, grad_accum=8` with QLoRA held in reserve as the OOM-recovery path — until either the hardware relaxes (desktop 4090 / A100) or a single seed_00 run actually OOMs in practice. **If the repo moves to Apple Silicon (`arm64`)**, the entire fallback chain changes: no QLoRA at all, MPS instead of CUDA, llama.cpp serving instead of vLLM-via-WSL.

---

_Pinned versions today_: dataset `spiceland9e-v1.0.0` (sha256 `95f1ae448c693088…`) · pipeline `pipeline-v0.3.0` · next model run id `qwen3-4b-bf16-lora-s00-r0` (not yet executed).

**Relevant paths**: `D:\Github\accounting\eval\spiceland9e.jsonl` · `D:\Github\accounting\eval\sft\splits\seed_00__351199285\` · `D:\Github\accounting\models\recipes\qwen3_4b_seed00_bf16_lora.ipynb` · `D:\Github\accounting\.meta\hardware.md` · `D:\Github\accounting\.meta\devlog.md`.
