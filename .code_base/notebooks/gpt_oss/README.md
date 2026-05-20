# gpt-oss fine-tuning — exploratory recipe

Parallel path to [`models/recipes/dgx_spark/`](../../../models/recipes/dgx_spark/). Use this when you specifically want to fine-tune OpenAI's gpt-oss (20B / 120B MoE) family. **Production training** for the accounting project still goes through `models/recipes/dgx_spark/` — gpt-oss is not the r0/r1 substrate.

This directory exists because gpt-oss has its own version-pin requirements that conflict with our production r0 environment.

## Why a separate path

The Unsloth gpt-oss recipe pins:

| Package | r0 production env (dgx_spark) | gpt-oss env (this dir) |
|---|---:|---:|
| transformers | 5.9.0 (NGC default) | **4.56.2** |
| trl | 0.26.1 | **0.22.2** |
| tokenizers | (NGC default) | **0.22.x — 0.23.x** |
| torchao | **uninstalled** (PEFT/Qwen3 dispatcher needs it gone) | **>= 0.16.0** (MoE training needs it) |
| unsloth | 2026.5.5 PyPI | git main (fresher MoE patches) |
| unsloth_zoo | 2026.5.3 PyPI | git main |

These are mutually exclusive. Mixing them in one container breaks both. Hence: two launchers, two container names, two ports.

## Files

| File | Surface |
|------|---------|
| `gpt_oss_20b_fine_tuning.ipynb` | Unsloth's official gpt-oss-20B notebook (verbatim from `unslothai/notebooks/main/nb/gpt-oss-(20B)-Fine-tuning.ipynb`) |
| `launch.sh` | host-side launcher; NGC container + the gpt-oss pip pins + JupyterLab on `127.0.0.1:8889` |
| `README.md` | this file |

## Run

```bash
# from repo root
bash .code_base/notebooks/gpt_oss/launch.sh
```

`launch.sh` will:

1. Verify the NGC image is present (same `nvcr.io/nvidia/pytorch:25.11-py3` as r0).
2. **Refuse to start** if a sibling container (`accounting-r0` or `accounting-dgx-spark`) is currently using the GPU — gpt-oss-20B uses ~14 GB at QLoRA and ~44 GB at bf16-LoRA; you can't double-book the GPU on this single-GB10 host. Stop the other container first.
3. Launch as `accounting-gpt-oss` on port `127.0.0.1:8889` (intentionally different from r0's `:8888` so they could coexist on a multi-GPU host, just not this one).
4. Bind-mount the repo at `/workspace` and the host HF cache at `/workspace/.hf_cache`.
5. Inside the container: install the gpt-oss pin set verbatim from the notebook (uses `uv pip` for speed; the install takes ~2-3 min).
6. Start JupyterLab on `127.0.0.1:8889` with no token.

Override the port with `JUPYTER_PORT=9999 bash .code_base/notebooks/gpt_oss/launch.sh`.

## Connect

**Browser**: `http://127.0.0.1:8889/lab` → navigate to `.code_base/notebooks/gpt_oss/gpt_oss_20b_fine_tuning.ipynb`.

**VS Code**: Open the notebook in VS Code → `Cmd/Ctrl-Shift-P` → *Jupyter: Specify Jupyter Server for Connections* → *Existing* → `http://127.0.0.1:8889/?token=` (empty token) → select kernel.

## What the notebook does

Unsloth's reference recipe — verbatim from the Colab. Loads `unsloth/gpt-oss-20b` (NOT `openai/gpt-oss-20b` — the Unsloth-prefixed variant has the pre-quantization + chat template that Unsloth's patches expect) with `load_in_4bit=True`, applies LoRA r=8/α=16 on the standard 7 target modules (q/k/v/o + gate/up/down), and trains on a small reasoning dataset.

**To adapt for the accounting project** (when/if we ever produce a gpt-oss baseline):

1. Replace the dataset cell with our v1.1.0 splits at `/workspace/eval/sft/splits/seed_00__351199285/`. The chat-template render in our `eval/_format.py` is compatible.
2. Set `output_dir = "/workspace/models/runs/gpt-oss-20b-4bit-qlora-s00-r0"`.
3. Emit Leo's standard manifest at the end (mirror the §8 cell from `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb`).
4. Run Vera's `eval/run.py` against the new run id for the slice-table A/B vs r0.

This is exploratory until a Vera slice-table shows gpt-oss-20b beats Qwen3-4B on our test split — at which point Leo would promote it to `models/recipes/gpt_oss/` per the standard promotion path in his agent file.

## Why this is NOT the Studio path

[Unsloth Studio's](../../../.meta/install_notes/unsloth_studio_aarch64/) trainer wraps `FastLanguageModel.from_pretrained()` without exposing `attn_implementation` ([studio/backend/core/training/trainer.py:824](../../../.meta/install_notes/unsloth_studio_aarch64/) — the final text-model branch). Unsloth's gpt-oss handler sets MoE-specific env vars and dtype overrides but does not force `attn_implementation="eager"`, which is what `GptOssForCausalLM` requires for now. Studio's `hardware.py` has a resolver that COULD pick "eager" — but it's wired to VRAM estimation, not back to the trainer's load call.

Path forward in Studio (when/if upstream fixes this):

- watch [github.com/unslothai/unsloth](https://github.com/unslothai/unsloth) for the gpt-oss attn-implementation auto-resolution patch
- when shipped: `~/.unsloth/studio/unsloth_studio/bin/pip install --upgrade --no-deps unsloth unsloth_zoo`
- retry in Studio with model name `unsloth/gpt-oss-20b`

Until then, this dir is the working path.

## Hardware budget

| Method | VRAM | This host |
|--------|------|-----------|
| gpt-oss-20b QLoRA (4-bit) | ~14 GB | trivial in 120 GB UMA |
| gpt-oss-20b bf16 LoRA | ~44 GB | comfortable |
| gpt-oss-120b QLoRA (4-bit) | ~65 GB | feasible (50%+ of unified pool) |
| gpt-oss-120b bf16 LoRA | not viable on single GB10 | exceeds 120 GB |

QLoRA r=8 on 20B is the recommended first try. Bump to r=16 if the notebook's r=8 underfits on the accounting domain.

## UMA OOM-recovery

Same as for r0 — page-cache pressure on the 120 GB unified pool can starve the GPU. Playbook-documented flush:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

Not an OOM-kill. Do this first before reducing `max_seq_length` or batch size.

## Notebook provenance

Source: `https://github.com/unslothai/notebooks/blob/main/nb/gpt-oss-(20B)-Fine-tuning.ipynb`
Downloaded: 2026-05-20.
Not edited; if/when we adapt it for the accounting corpus, do that adaptation in a sibling notebook (e.g. `gpt_oss_20b_accounting.ipynb`) and keep this one as the upstream-reference baseline.
