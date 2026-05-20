#!/usr/bin/env bash
# DGX Spark — launch NGC PyTorch container with the repo + HF cache bind-mounted
# and JupyterLab listening on :8888 (no token, host-bound only).
#
# Substrate-of-record: NVIDIA DGX Spark Unsloth playbook (NGC PyTorch 25.11-py3).
# This script is the DURABLE surface; the notebook inside the container is the
# experimental surface. Keep this minimal.
#
# Run:    bash models/recipes/dgx_spark/launch.sh
# Stop:   Ctrl+C in this terminal, or `docker stop accounting-dgx-spark` elsewhere.

set -euo pipefail

# ── paths (host) ──────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HF_CACHE_HOST="${HF_HOME:-${HOME}/.cache/huggingface}"
mkdir -p "${HF_CACHE_HOST}"

# ── image + container ────────────────────────────────────────────────────────
IMAGE="nvcr.io/nvidia/pytorch:25.11-py3"
CONTAINER_NAME="accounting-dgx-spark"
JUPYTER_PORT="${JUPYTER_PORT:-8888}"

# Pull only if not present locally (smoke test already pulled this).
docker image inspect "${IMAGE}" >/dev/null 2>&1 || docker pull "${IMAGE}"

# Kill any stale container of the same name (rerun-safe).
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# Inside-container bootstrap. Installs Unsloth via the playbook's --no-deps
# discipline, then launches JupyterLab. The trailing exec keeps the container
# attached so Ctrl+C in this terminal stops it cleanly.
read -r -d '' BOOTSTRAP <<'BASH' || true
set -euo pipefail
export HF_HOME=/workspace/.hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTHONUNBUFFERED=1
# Clean stale Unsloth runtime patcher cache from prior runs.
# Regenerates on first import (~5 s). Avoids subtle mismatches between cached
# patched trainers and the freshly-pip-installed Unsloth version. Path is the
# bind-mounted host dir; .gitignore already excludes it from the repo.
rm -rf /workspace/unsloth_compiled_cache/
pip install --quiet jupyterlab ipywidgets transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"
pip install --quiet --no-deps unsloth unsloth_zoo bitsandbytes
# NGC 25.11 ships torchao 0.14.0+git. PEFT >=0.18's `is_torchao_available()`
# RAISES on version <0.16; transformers 5.9.0's quantizer_torchao import path
# requires `torchao.prototype.safetensors` which doesn't exist in torchao 0.17+.
# Cleanest fix: uninstall torchao so both gracefully skip the dispatcher.
# Unsloth's 4-bit path goes through bitsandbytes, not torchao.
pip uninstall --quiet -y torchao || true
exec jupyter lab --no-browser --ip=0.0.0.0 --port=8888 --allow-root \
                 --ServerApp.token='' --ServerApp.password='' \
                 --ServerApp.root_dir=/workspace
BASH

echo "Launching ${CONTAINER_NAME} from ${IMAGE}"
echo "  repo  : ${REPO_ROOT} -> /workspace"
echo "  HF$   : ${HF_CACHE_HOST} -> /workspace/.hf_cache"
echo "  port  : 127.0.0.1:${JUPYTER_PORT} -> :8888 (container)"
echo
echo "Connect:"
echo "  Browser  : http://127.0.0.1:${JUPYTER_PORT}/lab"
echo "  VS Code  : Cmd-Shift-P -> 'Jupyter: Specify Jupyter Server' ->"
echo "             http://127.0.0.1:${JUPYTER_PORT}/?token=  (empty token)"
echo "             then open models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb"
echo

# --gpus all                 : GB10 visibility
# --ulimit memlock=-1        : unlimited pinned memory (UMA)
# --ulimit stack=67108864    : 64 MB stack (playbook requirement)
# --ipc=host                 : SHM for PyTorch DataLoader (avoids 64 MB default)
# -p 127.0.0.1:PORT:8888     : Jupyter on loopback only (no LAN exposure)
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
