# Hardware profile

_Probed 2026-05-20._

## Compute

| | |
|---|---|
| **CPU** | Intel Core i9-13900HX (Raptor Lake, 13th gen) — 24 cores (8 P + 16 E), 32 threads, base 2.2 GHz |
| **CPU arch** | **`x86_64`** (raw `AMD64` on Windows), **64-bit**, vendor=**Intel** |
| **RAM** | 64 GB DDR5-5600 (2× 32 GB DIMMs) |
| **GPU (CUDA)** | NVIDIA RTX 4090 Laptop — 16 GB GDDR6, sm_89 (Ada), 76 SMs, driver 581.95 |
| **GPU (iGPU)** | Intel UHD Graphics (Raptor Lake-S) — used for display, not compute |
| **OS** | Windows 11 Home build 26200 (64-bit) |
| **Python bitness** | 64-bit (matches OS — no 32/64 mismatch) |

**ML stack compatibility under this arch**: `x86_64` Intel is the full-support
path. `bitsandbytes` (NF4/INT8), `flash-attn`, and AVX2/AVX-512 GEMM kernels
all work. QLoRA fallback is available as the OOM-recovery path if bf16-LoRA
gets tight on 16 GB VRAM. If the repo ever moves to `arm64` (Apple Silicon or
Linux ARM), this row needs updating and the QLoRA fallback disappears (no ARM
build of bitsandbytes). See ROADMAP §4 for the per-arch algorithm matrix.

## Storage

| Drive | Total | Free | % free | Disk |
|-------|------:|-----:|------:|------|
| `C:` | 929 GB | 105 GB | 11% | Crucial P1 1 TB NVMe SSD |
| `D:` | 931 GB | 167 GB | 18% | Samsung 970 EVO Plus 1 TB NVMe SSD |

`D:` (where the project lives) has ample headroom for the fine-tune: HF cache (~3 GB), 5-seed adapter checkpoints (~5 GB total), training logs + eval outputs (~2 GB) all fit comfortably. `C:` is workable but tighter — if you ever need to spill cache, set `HF_HOME=D:\hf_cache` to keep it on the larger free-space drive.

## Python environments

| Env | Python | Role | Path |
|-----|--------|------|------|
| **system / base** | 3.13.3 | Data-pipeline scripts (`eval/extract_word_tables.py`, `ingest_spiceland.py`, `split_multi_seed.py`) | `C:\Python313\python.exe` |
| **`unsloth`** *(active for fine-tune)* | 3.12.9 | Training + adapter inference | `C:\Users\huang\anaconda3\envs\unsloth\python.exe` |

## ML stack — `unsloth` env

```
python       : 3.12.9
torch        : 2.8.0+cu126
cuda visible : NVIDIA RTX 4090 Laptop GPU, 16 GB, sm_89
```

| Package | Status | Used for |
|---------|--------|----------|
| `unsloth` | ✅ 2025.11.1 | 2× faster fine-tune, model loading |
| `transformers` | ✅ 4.57.1 | HF model + tokenizer + Trainer |
| `peft` | ✅ 0.17.1 | LoRA adapter config |
| `trl` | ✅ 0.23.0 | `SFTTrainer`, `DataCollatorForCompletionOnlyLM` |
| `bitsandbytes` | ✅ 0.48.2 | 4-bit NF4 base for QLoRA |
| `accelerate` | ✅ 1.11.0 | Multi-GPU / mixed-precision orchestration |
| `datasets` | ✅ 4.4.0 | JSONL loader (sanity-loaded `eval/sft/splits/seed_00__*/{train,valid,test}.jsonl` → 3,537 / 450 / 464 records ✅) |
| `xformers` | ✅ 0.0.32.post2 | Memory-efficient attention kernels |
| `torch` | ✅ 2.8.0+cu126 | Foundation |
| `tiktoken` | ✅ 0.13.0 | Exact token-count audits |
| `seedhash` | ✅ 0.1.0 | Re-run `split_multi_seed.py` from this env |
| `vllm` | ❌ **must remain uninstalled on Windows** | The Windows wheel installs the Python files but ships no `vllm._C` (the native C extension is Linux-only). When present, it triggers `ModuleNotFoundError: No module named 'vllm._C'` during `import unsloth` because `unsloth_zoo/vllm_utils.py:91` gates its patching block on `importlib.util.find_spec("vllm")` — which says yes even when the C ext is broken — and then hits an unguarded `import vllm.model_executor...` at line 152. For production serving on Windows, use llama.cpp (GGUF export from Unsloth) or run vLLM inside WSL/Docker. |

## ML stack — system Python 3.13.3 (data pipeline only)

```
torch        : 2.9.1+cu126
seedhash     : 0.1.0   ← used by eval/split_multi_seed.py
openpyxl     : 3.1.5   ← used by eval/ingest_spiceland.py
python-docx  : 1.2.0   ← used by eval/extract_word_tables.py + ingest
```

This env is what produced the canonical JSONL and the multi-seed SFT splits. It's **not** the fine-tuning env — keep it for data-pipeline re-runs only.

## Fine-tune feasibility — Qwen3-4B SFT-LoRA (Leo's recommended recipe)

**Verdict: feasible locally.** Single-seed pilot ≈ 35–60 min on this hardware; full 5-seed sweep ≈ 3–5 hours. No cloud needed.

### VRAM accounting (16 GB available)

| Component | Estimated VRAM |
|-----------|---------------:|
| Qwen3-4B base in bf16 | ~8.0 GB |
| LoRA adapters (rank 16, 7 modules) | ~0.05 GB |
| Activations (batch=2, seq=3072, bf16) | ~4.0 GB |
| KV cache (training-time, gradient checkpointing on) | ~1.5 GB |
| Optimizer state (AdamW, fp32 on LoRA params only) | ~0.2 GB |
| **Headroom for fragmentation / spikes** | ~2.2 GB |
| **Total** | ~16 GB (tight but workable) |

To create comfortable headroom:
- **QLoRA (4-bit NF4 base)** → cuts base from 8 GB → 2.2 GB, frees ~6 GB. Recommended if the bf16 LoRA OOMs.
- **`max_seq_length=2048`** instead of 3072 → covers p95=605 with 3× margin; only the single 2,310-token outlier truncates.
- **`per_device_train_batch_size=1, grad_accum=16`** → halves activation memory; same effective batch.

### CPU / RAM are not the bottleneck

- 24 cores is overkill for the dataloader; setting `dataloader_num_workers=8` is sufficient.
- 64 GB DDR5 means CPU offload (e.g. `accelerate` offload for evaluation) is available if VRAM ever gets contended.

### Constraints / risks to know

1. **`unsloth` env is on Python 3.12.9** — matches Leo's recommendation. Wheel compatibility is solid (no source builds needed). System Python 3.13.3 is unaffected and continues to drive the data pipeline.
2. **RTX 4090 Laptop ≠ desktop 4090.** It has 16 GB VRAM (vs 24 GB) and a tighter power envelope (~150 W TGP vs 450 W). Throughput is ~60% of the desktop card. Cost-per-token-trained is still excellent for LoRA-class workloads.
3. **`sm_89` (Ada) supports FP8.** When you scale beyond LoRA (e.g. full FT), the hardware can do FP8 mixed-precision — but Qwen3-4B LoRA doesn't need it.
4. **Disk space is comfortable (~167 GB free on D:).** No action needed. Planned footprint: HF cache (~3 GB), 5 seed × adapter checkpoint (~1 GB each = 5 GB), training logs (~500 MB), evaluation outputs (~1 GB) — total ~10 GB against 167 GB free.
5. **Triton emits non-fatal warnings about `cuobjdump.exe` / `nvdisasm.exe` not found.** These are debug binaries; runtime kernels work fine. Ignore.

## Activate the fine-tune env

```powershell
conda activate unsloth
# or run scripts directly with:
& "C:\Users\huang\anaconda3\envs\unsloth\python.exe" <script.py>
```

Verify (one-liner):

```powershell
& "C:\Users\huang\anaconda3\envs\unsloth\python.exe" -c "from unsloth import FastLanguageModel; import torch; print(torch.cuda.get_device_name(0))"
# Expected: NVIDIA GeForce RTX 4090 Laptop GPU
```

The full env profile is reproducible via `eval/_audit/probe_env.py`.

## Serving the trained adapter (Windows-friendly paths)

vLLM is the production-grade serving stack but does **not** work on Windows (see the
table above). Windows-compatible options:

| Path | How |
|------|-----|
| **Unsloth inference** (simplest, same env) | `FastLanguageModel.for_inference(model)` after `from_pretrained` of the saved adapter |
| **llama.cpp / GGUF** (CPU + GPU, no extra env) | Export with `model.save_pretrained_gguf(...)` from Unsloth, run with `llama.cpp` or `Ollama` |
| **vLLM via WSL2** | Set up Ubuntu WSL2, `pip install vllm` there, serve from inside WSL; mount the Windows adapter dir |
| **vLLM via Docker Desktop** | Pull `vllm/vllm-openai:latest`, mount the adapter dir into the container |

## Serving the trained adapter

| Path | Stack | Notes |
|------|-------|-------|
| **Production** | vLLM + AWQ-4bit | sm_89 supports AWQ kernels natively; throughput ~150 tok/s on 4090 Laptop for 4B model |
| **Local dev** | `unsloth` `FastLanguageModel.for_inference()` | Same Python env as training; quickest iteration |
| **CPU-only test** | llama.cpp (GGUF) | If you want to verify the adapter works without firing up CUDA |

## Bottom line

**Ready to launch.** The `unsloth` env (Python 3.12.9) has every package Leo's recipe needs — `unsloth 2025.11.1`, `transformers 4.57.1`, `peft 0.17.1`, `trl 0.23.0`, `bitsandbytes 0.48.2`, `accelerate 1.11.0`, `datasets 4.4.0`, `xformers 0.0.32.post2`, `torch 2.8.0+cu126` — and it can already load the multi-seed SFT splits (verified 3,537 / 450 / 464 records). Disk has 167 GB free on `D:`, default to QLoRA for the 16 GB VRAM budget, and a single-seed pilot will run in ~35-60 min.
