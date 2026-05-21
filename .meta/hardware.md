# Hardware profile

_Probed 2026-05-20. The repo is portable across Windows / macOS / Linux on x86_64 / arm64. Pat's session-start check (`.claude/agents/pat-pm.md` §"Session-start host check") identifies which row is **active** for the current session and points algorithm defaults at that row's prescribed path. All rows below are first-class supported targets; dormant rows are preserved for future runs on those platforms — **never retired**._

## Supported host platforms (compatibility matrix)

| Status | Host | OS | CPU arch | GPU | RAM | Prescribed recipe |
|--------|------|----|----------|-----|-----|-------------------|
| ★ **ACTIVE** | NVIDIA DGX Spark | Ubuntu 24.04 LTS aarch64 | ARM Neoverse V2 (20c, Grace) | NVIDIA GB10 Blackwell sm_120 | 119.6 GB UMA (CPU+GPU shared) | NGC container + 4-bit QLoRA — `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` |
| **dormant** | Windows + RTX 4090 Laptop | Windows 11 x86_64 | Intel i9-13900HX (24c/32t) | NVIDIA RTX 4090 Laptop sm_89 | 64 GB DDR5-5600 | Unsloth + bf16-LoRA — `models/recipes/qwen3_4b_seed00_bf16_lora.ipynb` |
| future | macOS Apple Silicon | macOS arm64 | Apple M-series | Apple MPS (unified memory) | unified | template TBD — bf16-LoRA only (no bitsandbytes on arm64), serve via llama.cpp/Ollama |
| future | Linux x86_64 + NVIDIA | Linux | Intel/AMD | any NVIDIA CUDA | discrete VRAM | template TBD — full Unsloth stack incl. vLLM |
| future | Linux x86_64 + AMD ROCm | Linux | AMD EPYC/Ryzen | AMD Instinct / MI | discrete VRAM | template TBD — Unsloth + bitsandbytes-rocm |
| future | Linux aarch64 (other) | Linux | ARM Neoverse / Ampere / etc. | varies | varies | template TBD — community ARM wheels |

**Source-of-truth pointers per row**:

- **★ ACTIVE — DGX Spark**: detailed below + the NVIDIA DGX Spark Unsloth playbook (<https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth>, last updated 2025-12-15).
- **dormant — Windows + RTX 4090 Laptop**: detailed in the [Dormant host details](#dormant-host-details--windows--rtx-4090-laptop) section below.
- **future** rows: populate when probe_host.py runs on that platform for the first time.

---

## Compute

| | |
|---|---|
| **Host** | NVIDIA DGX Spark — Grace-Blackwell GB10 superchip (Spark device) |
| **CPU** | ARM Neoverse V2 (20 cores; Grace side of GB10) |
| **CPU arch** | **`aarch64`** (`arm64`), **64-bit**, vendor=**NVIDIA Grace** |
| **RAM** | **119.6 GB unified LPDDR5X** (Unified Memory Architecture — CPU/GPU share) |
| **GPU (CUDA)** | NVIDIA GB10 Blackwell — sm_120 (compute_cap 12.1), driver 580.95.05, CUDA 13.0 |
| **OS** | Ubuntu 24.04 LTS (aarch64) |
| **Python bitness** | 64-bit (conda base, Python 3.13.11) |

**ML stack compatibility under this arch.** The DGX Spark Unsloth
playbook prescribes the **NGC PyTorch container** as the substrate;
the container already ships PyTorch + CUDA 13.0 + sm_120 kernels +
Triton, so `unsloth`, `unsloth_zoo`, and `bitsandbytes` install with
`--no-deps` against container-managed wheels. No host-side pip
resolution; aarch64 wheel-set fragility on bare metal is bypassed
entirely by going through the container.

**Unified Memory Architecture (UMA).** GPU and CPU share the 119.6
GB LPDDR5X pool dynamically — there is no separate "VRAM" budget;
the same bytes back both. This unlocks 70B-class adapter
fine-tuning at 4-bit that an x86_64 / discrete-GPU host cannot
touch on a single card. The tradeoff is that page-cache pressure
from one side starves the other; OOM-recovery is a buffer-cache
flush (see below), not an OOM-kill.

## Storage

| Mount | Total | Free | % free | Notes |
|-------|------:|-----:|------:|------|
| repo root | — | **2,210 GB free** | — | Ample headroom — HF cache (~5 GB), 5-seed adapter checkpoints (~5 GB), 70B-class 4-bit base (~40 GB) all fit comfortably. |

Set `HF_HOME` inside the container to a host-mounted path so the
weight cache survives container restarts.

## Python environments

| Env | Python | Role |
|-----|--------|------|
| **host conda base** | 3.13.11 | Data-pipeline scripts (`eval/extract_word_tables.py`, `ingest_spiceland.py`, `split_multi_seed.py`); the ETL boundary lives here. |
| **NGC container `nvcr.io/nvidia/pytorch:25.11-py3`** | container-managed | Training + adapter inference + vLLM serving. All ML work runs inside the container; the host conda env is read-only with respect to ML wheels. |

Two-env split is preserved across the platform change — the data
pipeline still runs host-side; the trainer runs inside the
container. The boundary is the JSONL artifact, sha256-pinned, same
as before.

## ML stack — NGC container (substrate-of-record)

Verbatim from the NVIDIA DGX Spark Unsloth playbook
(`<https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth>`,
last updated 2025-12-15):

```bash
# Step 2: container
docker pull nvcr.io/nvidia/pytorch:25.11-py3

# Step 3: launch
docker run --gpus all --ulimit memlock=-1 -it --ulimit stack=67108864 \
  --entrypoint /usr/bin/bash --rm nvcr.io/nvidia/pytorch:25.11-py3

# Step 4: dependencies inside container
pip install transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"
pip install --no-deps unsloth unsloth_zoo bitsandbytes
```

The `--no-deps` flag is critical: the NGC container ships
container-managed PyTorch + CUDA 13.0 + sm_120 Triton kernels, and
the `unsloth`/`unsloth_zoo`/`bitsandbytes` wheels must NOT pull a
host-resolved PyTorch on top. Pip resolution under aarch64 would
also miss the sm_120 build path. Trust the container's wheel set.

| Package | Source | Used for |
|---------|--------|----------|
| `torch` | container-managed | Foundation (CUDA 13.0, sm_120 kernels) |
| `triton` | container-managed | sm_120-compatible kernels for Unsloth |
| `unsloth` | `pip install --no-deps` | 2-5× speedup; auto-enabled DGX Spark optimizations per `unsloth.ai/blog/nvidia-collab` |
| `unsloth_zoo` | `pip install --no-deps` | Patches + helpers |
| `bitsandbytes` | `pip install --no-deps` | NF4 4-bit base, `adamw_8bit` optimizer |
| `transformers` | `pip install` | HF model + tokenizer + Trainer |
| `peft` | `pip install` | LoRA adapter config |
| `trl` | `pip install ==0.26.1` | `SFTTrainer` (playbook-pinned version) |
| `datasets` | `pip install ==4.3.0` | JSONL loader (playbook-pinned version) |
| `hf_transfer` | `pip install` | Fast HF Hub download |
| `vllm` | container-compatible | Production serving stack; runs natively in the Linux aarch64 container. Available on this row; the dormant Windows row has no `vllm._C` so its prescribed stack is Unsloth-native + llama.cpp/Ollama instead. |

### Validated patterns (from playbook `test_unsloth.py`)

- `from unsloth import FastLanguageModel, FastModel` — both available.
- `FastModel.from_pretrained(model_name, max_seq_length=2048, load_in_4bit=True, load_in_8bit=False, full_finetuning=False)` — 4-bit QLoRA is the validated first-class path.
- `FastLanguageModel.get_peft_model(...)` with `use_gradient_checkpointing="unsloth"`.
- `SFTTrainer` from `trl==0.26.1` with `optim="adamw_8bit"`.
- Playbook reference recipe: `unsloth/Phi-3.5-mini-instruct`, 4-bit, LoRA r=16, `q,k,v,o,gate,up,down`, `lora_alpha=16`, `lora_dropout=0`, batch=2, grad_accum=4, `max_steps=60`, `max_seq_length=2048`.

### Pre-quantized 4-bit models the playbook explicitly supports

Llama-3.1-8B / 70B / 405B-bnb-4bit, Mistral-Small-Instruct-2409
(22B), Mistral-7B, Phi-3.5-mini, Phi-3-medium, Gemma-2-9B / 27B,
Llama-3.2-1B / 3B, **Llama-3.3-70B-Instruct-bnb-4bit**. Qwen3 is
not in the explicit list but the broader Unsloth FastLanguageModel
path covers it (the `unsloth.ai/blog/nvidia-collab` post
explicitly benchmarks Qwen3-14B QLoRA SFT with a +14.3%
per-batch speedup on DGX Spark).

### Unsloth on DGX Spark — disclosed deltas

From `unsloth.ai/blog/nvidia-collab`:

- Optimizations **auto-enabled** on DGX Spark machines; no flag needed.
- **~25% speedup on top of the existing 2-5× vs HF Trainer**, no accuracy loss.
- Specifically validated: Qwen3-14B QLoRA SFT (+14.3% per-batch), Qwen3-0.6B, Llama-3.2-1B, GPT-OSS (MoE-specific).
- Double-buffered checkpointing overhead: **+0.37 GB at 8B**, **+0.47 GB at 14B**, **+0.23 GB at 32B**.
- No aarch64-specific kernel work disclosed — the speedup is shared across x86 and Grace-Blackwell, implying the existing Triton kernels are sm_120-compatible via the container's CUDA 13.0 + recent Triton.

### UMA OOM-recovery (documented in playbook)

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

Playbook note (verbatim): "DGX Spark uses a Unified Memory
Architecture (UMA), which enables dynamic memory sharing between
the GPU and CPU. With many applications still updating to take
advantage of UMA, you may encounter memory issues even when within
the memory capacity of DGX Spark." The flush drops the page cache
to give the GPU back its share. Run this between back-to-back
training launches; it is cheap and the documented first response
to UMA OOMs.

## ML stack — host conda base (data pipeline only)

| Package | Status |
|---------|--------|
| `psutil` | ✅ |
| `torch` | ❌ (not needed host-side) |
| `transformers` / `peft` / `trl` / `unsloth` / `bitsandbytes` / `accelerate` / `datasets` / `vllm` | ❌ (intentionally absent; ML work lives in the container) |
| `seedhash` | (re-install if `split_multi_seed.py` re-runs) |
| `openpyxl` | (re-install if `ingest_spiceland.py` re-runs) |
| `python-docx` | (re-install if `extract_word_tables.py` re-runs) |

The eval data + ETL artifacts survived the platform move:
`eval/spiceland9e.jsonl` sha256 still matches the
`spiceland9e-v1.0.0` anchor `95f1ae448c693088…`; all 5 seed splits
intact per `eval/sft/splits/manifest.json`.

## Fine-tune feasibility

**Verdict (this row only): feasible locally, with substantially expanded ceiling.**
The 119.6 GB UMA pool plus playbook-validated 4-bit QLoRA via
`FastModel.from_pretrained(load_in_4bit=True)` puts targets unreachable
on the Windows dormant row's 16 GB VRAM ceiling now within reach on
the DGX Spark active row.

### UMA accounting (119.6 GB unified pool)

| Component | Estimated footprint (4-bit QLoRA path) |
|-----------|---------------------------------------:|
| **Qwen3-4B** 4-bit base | ~2.2 GB |
| **Llama-3.1-8B** 4-bit base | ~4.5 GB |
| **Mistral-Small-22B** 4-bit base | ~12 GB |
| **Llama-3.3-70B** 4-bit base | **~40 GB** |
| LoRA adapters (rank 16, 7 modules, bf16) | ~0.05-0.2 GB depending on base |
| Activations (batch=2, seq=2048, bf16, grad-ckpt on) | ~2-6 GB depending on base |
| Optimizer (`adamw_8bit`, LoRA params only) | ~0.1-0.5 GB |
| Unsloth double-buffer overhead | +0.37 GB (8B), +0.47 GB (14B), +0.23 GB (32B) |
| OS + CPU working set | ~20-30 GB |
| **Headroom on 119.6 GB UMA** | ample for 4B-32B; tight-but-workable for 70B with UMA flush in standby |

### Constraints / risks specific to this host

1. **UMA pressure, not VRAM OOM.** Failure mode is CPU/GPU starving each other through the page cache, not a hard CUDA OOM. First response is the documented buffer-cache flush above; do not jump to `max_seq_length` reduction until the flush is tried.
2. **`--no-deps` is load-bearing.** Any future `pip install unsloth` without `--no-deps` inside the container will pull a host-resolved PyTorch on top of the container's, breaking the sm_120 Triton path. The recipe enforces this.
3. **CUDA 13.0 / sm_120 is bleeding edge.** Anything that pins `cuda-12.x` or `compute_cap < 12.0` is incompatible. The container is the abstraction that hides this from the recipe.
4. **Disk is comfortable (~2,210 GB free).** No action needed even at 70B-class footprints.

## Launch the fine-tune env

```bash
docker pull nvcr.io/nvidia/pytorch:25.11-py3
docker run --gpus all --ulimit memlock=-1 -it --ulimit stack=67108864 \
  --entrypoint /usr/bin/bash --rm nvcr.io/nvidia/pytorch:25.11-py3
# inside container:
pip install transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"
pip install --no-deps unsloth unsloth_zoo bitsandbytes
python -c "from unsloth import FastLanguageModel; import torch; print(torch.cuda.get_device_name(0))"
# Expected: NVIDIA GB10 (or the playbook-equivalent device name)
```

## Serving the trained adapter

| Path | Stack | Notes |
|------|-------|-------|
| **Production batch eval** | vLLM (inside container) | Continuous batching + paged KV cache; native sm_120 via CUDA 13.0. Back on the menu — the Windows blocker is gone. |
| **Local dev / iteration** | `FastLanguageModel.for_inference(model)` | Same container as training; quickest iteration. |
| **CPU-only / portable test** | llama.cpp (GGUF export from Unsloth) | If a quick sanity-check without firing up the container is wanted. |
| **AWQ-4bit on vLLM** | AWQ → vLLM | sm_120 supports AWQ kernels; recovery-vs-fp16 score recorded on the 200-q probe before production swap. |

## Bottom line — ACTIVE row

**Ready to launch on the active row's prescribed substrate.** The NVIDIA DGX
Spark Unsloth playbook (URL above, last updated 2025-12-15) is the
prescribed path for this row. The substrate is: NGC container
`nvcr.io/nvidia/pytorch:25.11-py3` + `pip install --no-deps unsloth
unsloth_zoo bitsandbytes` + 4-bit QLoRA via `FastModel.from_pretrained`
+ `adamw_8bit` + `SFTTrainer` from `trl==0.26.1`. The 119.6 GB UMA
pool permits a 70B-class 4-bit adapter fine-tune on this row, which
the Windows dormant row's 16 GB VRAM cannot reach — different rows,
different ceilings, both first-class.

Eval data + ETL artifacts are platform-agnostic and survived intact across
the row switch: `eval/spiceland9e.jsonl` sha `95f1ae448c693088…` matches
the `spiceland9e-v1.0.0` anchor; all 5 seed splits verified.

---

## Dormant host details — Windows + RTX 4090 Laptop

Last active 2026-05-19. Preserved as a first-class supported target; the
bf16-LoRA recipe at `models/recipes/qwen3_4b_seed00_bf16_lora.ipynb` remains
the prescribed path when the repo runs on this host again. Detailed
configuration:

| | |
|---|---|
| **Host** | Personal workstation, Windows 11 |
| **CPU** | Intel Core i9-13900HX (Raptor Lake, 13th gen) — 24 cores (8 P + 16 E), 32 threads, base 2.2 GHz |
| **CPU arch** | `x86_64` (raw `AMD64` on Windows), 64-bit, vendor=**Intel** |
| **RAM** | 64 GB DDR5-5600 (2× 32 GB DIMMs) |
| **GPU (CUDA)** | NVIDIA RTX 4090 Laptop — 16 GB GDDR6, sm_89 (Ada), 76 SMs, driver 581.95 |
| **OS** | Windows 11 Home build 26200, 64-bit |
| **Python env** | conda `unsloth` env on Python 3.12.9, torch 2.8.0+cu126 |

**Row-specific prescribed path** (when this row is ACTIVE):

- Substrate: native Windows + Unsloth in the `unsloth` conda env (NOT a container).
- Quantization: bf16 LoRA at `r=16, batch=2, seq=2048, grad_accum=8`; QLoRA held as OOM-recovery fallback.
- Serving: Unsloth-native inference, llama.cpp/Ollama for portable runs. **vLLM is NOT available on Windows** (`vllm._C` is Linux-only; presence breaks `import unsloth` via `unsloth_zoo/vllm_utils.py:91-152` — the recipe asserts `find_spec("vllm") is None`).
- DataLoader: `num_workers=0` (Windows uses spawn which re-imports the notebook module).
- HF cache: `HF_HOME=D:\hf_cache` so the ~4 GB base download goes to the larger free-space drive.

**Row-specific limits** (when this row is ACTIVE):

- 16 GB VRAM ceiling: rules out 7B+ in bf16, all full FT, batch>2 at seq 2048.
- ~50-70 min per epoch on Qwen3-4B-LoRA; ~$0/$1.50/$3 per seed if measured against rental A100 pricing.

The full Windows-host profile that drove the initial ETL + the `qwen3_4b_seed00_bf16_lora.ipynb` recipe lives in git history at commit `77382a02` (initial commit) and is recoverable in full via `git show 77382a02:.meta/hardware.md` if a Windows-targeted run needs deeper context.

---

## Future host details — templates

When a `future` row in the matrix becomes ACTIVE for the first time, populate
this section with the same shape as the Dormant section above. The
`probe_host.py` output for that host plus the per-row prescribed path
(quantization choice, serving stack, DataLoader posture, HF cache location)
goes here, and the corresponding row in the matrix flips `future` → `★ ACTIVE`
while the previous ★ flips to `dormant`.

Templates for the unconfigured rows:

- **macOS Apple Silicon**: torch.backends.mps, unified memory == effective VRAM,
  no bitsandbytes (no QLoRA path), no flash-attn, bf16 LoRA only, serve via
  llama.cpp/Ollama.
- **Linux x86_64 + NVIDIA**: full stack — bf16 or 4-bit, flash-attn, FP8 on
  Ada/Hopper, vLLM serving native. Fork-based multiprocess permits
  `dataloader_num_workers > 0`.
- **Linux x86_64 + AMD ROCm**: vLLM (ROCm build) + bitsandbytes-rocm +
  flash-attn AMD fork.
- **Linux aarch64 (non-DGX)**: partial — bitsandbytes via community ARM build,
  no flash-attn, PyTorch ARM wheels OK.
