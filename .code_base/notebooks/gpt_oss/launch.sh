#!/usr/bin/env bash
# gpt-oss fine-tuning launcher — DGX Spark, NGC PyTorch container, with the
# version pins from Unsloth's official gpt-oss notebook.
#
# This is a PARALLEL path to models/recipes/dgx_spark/launch.sh:
#   - dgx_spark/launch.sh runs our PRODUCTION r0 recipe:
#       transformers 5.9 · trl 0.26 · torchao UNINSTALLED · uniform loss
#   - this launcher runs the gpt-oss recipe:
#       transformers 4.56.2 · trl 0.22.2 · torchao>=0.16.0 · MoE-aware patches
#
# Two containers with the same NGC base but different pip environments —
# different ports so they can coexist. r0 lives in nvcr.io/nvidia/pytorch:25.11-py3
# with our pins; this lives in the SAME image with the gpt-oss pins.
#
# Run:    bash .code_base/notebooks/gpt_oss/launch.sh
# Stop:   Ctrl+C, or `docker stop accounting-gpt-oss` elsewhere.

set -euo pipefail

# ── paths (host) ──────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HF_CACHE_HOST="${HF_HOME:-${HOME}/.cache/huggingface}"
mkdir -p "${HF_CACHE_HOST}"

# ── image + container ────────────────────────────────────────────────────────
IMAGE="nvcr.io/nvidia/pytorch:25.11-py3"
CONTAINER_NAME="accounting-gpt-oss"
JUPYTER_PORT="${JUPYTER_PORT:-8889}"      # not :8888 — leaves r0/dgx_spark slot free

# Pull only if not present locally.
docker image inspect "${IMAGE}" >/dev/null 2>&1 || docker pull "${IMAGE}"

# Refuse to start if our production r0 container is running — they'd contend for GPU.
if docker ps --format '{{.Names}}' | grep -qE '^accounting-(r0|dgx-spark)$'; then
    echo "ERROR: a sibling container is already using the GPU:" >&2
    docker ps --filter "name=accounting-" --format "  {{.Names}}\t{{.Status}}" >&2
    echo "Stop it first (docker stop ...), then re-run this script." >&2
    exit 1
fi

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# Inside-container bootstrap. Mirrors the Unsloth gpt-oss notebook's exact pip
# install lines (verbatim from the official Colab) so versions match what's
# validated upstream. Major divergence from dgx_spark/launch.sh:
#   - transformers 4.56.2 (not 5.9) — gpt-oss SDPA support landed here
#   - trl 0.22.2 (not 0.26.1) — gpt-oss trainer compatibility
#   - torchao >= 0.16.0 INSTALLED (not uninstalled) — MoE training needs it
#   - unsloth + unsloth_zoo from git main — fresher MoE patches than PyPI
read -r -d '' BOOTSTRAP <<'BASH' || true
set -euo pipefail
export HF_HOME=/workspace/.hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTHONUNBUFFERED=1

# Clean stale Unsloth runtime patcher cache from prior runs (regenerates).
rm -rf /workspace/unsloth_compiled_cache/

# Use uv for speed; mirrors Unsloth's own install flow.
pip install --quiet --upgrade uv

# Core deps — from the official gpt-oss notebook cell 4.
uv pip install --quiet --system \
    "torch>=2.8.0" "triton>=3.4.0" numpy pillow torchvision bitsandbytes \
    "transformers==4.56.2" \
    "unsloth_zoo[base] @ git+https://github.com/unslothai/unsloth-zoo" \
    "unsloth[base] @ git+https://github.com/unslothai/unsloth" \
    "git+https://github.com/triton-lang/triton.git@0add68262ab0a2e33b84524346cb27cbb2787356#subdirectory=python/triton_kernels"

# --no-deps pin overrides — matches the notebook's second pip line.
uv pip install --quiet --system --no-deps --upgrade \
    "transformers==4.56.2" \
    "tokenizers>=0.22.0,<=0.23.0" \
    "trl==0.22.2" \
    unsloth unsloth_zoo

uv pip install --quiet --system --no-deps --upgrade "torchao>=0.16.0"

# JupyterLab on top so we can open the notebook interactively.
pip install --quiet jupyterlab ipywidgets

exec jupyter lab --no-browser --ip=0.0.0.0 --port=8888 --allow-root \
                 --ServerApp.token='' --ServerApp.password='' \
                 --ServerApp.root_dir=/workspace
BASH

echo "Launching ${CONTAINER_NAME} from ${IMAGE}"
echo "  repo  : ${REPO_ROOT} -> /workspace"
echo "  HF\$  : ${HF_CACHE_HOST} -> /workspace/.hf_cache"
echo "  port  : 127.0.0.1:${JUPYTER_PORT} -> :8888 (container)"
echo
echo "Connect:"
echo "  Browser  : http://127.0.0.1:${JUPYTER_PORT}/lab"
echo "  VS Code  : Cmd-Shift-P -> 'Jupyter: Specify Jupyter Server' ->"
echo "             http://127.0.0.1:${JUPYTER_PORT}/?token=  (empty token)"
echo "             then open .code_base/notebooks/gpt_oss/gpt_oss_20b_fine_tuning.ipynb"
echo

exec docker run --rm --name "${CONTAINER_NAME}" \
    --gpus all \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --ipc=host \
    -p "127.0.0.1:${JUPYTER_PORT}:8888" \
    -v "${REPO_ROOT}:/workspace" \
    -v "${HF_CACHE_HOST}:/workspace/.hf_cache" \
    -w /workspace \
    "${IMAGE}" \
    bash -c "${BOOTSTRAP}"
