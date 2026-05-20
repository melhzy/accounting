#!/usr/bin/env bash
# eval/run_in_container.sh
# Host-side wrapper: docker-runs eval/run.py inside the NGC PyTorch container.
# Mirrors models/recipes/dgx_spark/launch.sh but headless (no JupyterLab).
#
# Usage:
#   bash eval/run_in_container.sh [--limit N] [extra run.py args...]
#
# Safety gates:
#   - Refuses if a training container (accounting-dgx-spark or accounting-r0)
#     is already running.
#   - Uses container name "accounting-eval" (distinct from training container).
#   - If no GPU is available for the eval container, warns and aborts.

set -euo pipefail

# ── paths (host) ───────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_CACHE_HOST="${HF_HOME:-${HOME}/.cache/huggingface}"
mkdir -p "${HF_CACHE_HOST}"

# ── image + container ──────────────────────────────────────────────────────
IMAGE="nvcr.io/nvidia/pytorch:25.11-py3"
EVAL_CONTAINER="accounting-eval"

# ── default eval arguments (override by appending args to this script) ─────
RUN_ID="qwen3-4b-4bit-qlora-s00-r0"
SPLIT="eval/sft/splits/seed_00__351199285/test.jsonl"
ADAPTER="models/runs/qwen3-4b-4bit-qlora-s00-r0"
EXTRA_ARGS=("$@")   # pass-through to run.py

# ── safety gate: refuse if a training container is running ─────────────────
TRAINING_CONTAINERS=("accounting-dgx-spark" "accounting-r0" "accounting-training")
for tc in "${TRAINING_CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${tc}$"; then
        echo "[run_in_container.sh] REFUSED: training container '${tc}' is currently running."
        echo "  Stop it first with:  docker stop ${tc}"
        echo "  (The eval container needs the full GPU; sharing with a training run risks OOM.)"
        exit 1
    fi
done

# ── safety gate: GPU must be available ────────────────────────────────────
if ! nvidia-smi >/dev/null 2>&1; then
    echo "[run_in_container.sh] REFUSED: nvidia-smi not available — no GPU detected."
    exit 1
fi

# ── pull image if not present ──────────────────────────────────────────────
docker image inspect "${IMAGE}" >/dev/null 2>&1 || {
    echo "[run_in_container.sh] Pulling ${IMAGE} ..."
    docker pull "${IMAGE}"
}

# ── kill any stale eval container ─────────────────────────────────────────
docker rm -f "${EVAL_CONTAINER}" >/dev/null 2>&1 || true

# ── container bootstrap (same pip discipline as training launch) ───────────
read -r -d '' BOOTSTRAP <<'BASH' || true
set -euo pipefail
export HF_HOME=/workspace/.hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTHONUNBUFFERED=1
rm -rf /workspace/models/recipes/dgx_spark/unsloth_compiled_cache/
pip install --quiet transformers peft hf_transfer "datasets==4.3.0" "trl==0.26.1"
pip install --quiet --no-deps unsloth unsloth_zoo bitsandbytes
pip uninstall --quiet -y torchao || true
exec python /workspace/eval/run.py \
    --run-id   "$RUN_ID" \
    --split    "/workspace/$SPLIT" \
    --adapter  "/workspace/$ADAPTER" \
    "${EXTRA_ARGS_JOINED[@]}"
BASH

# Inject shell variables into the bootstrap string safely
EXTRA_ARGS_JOINED_STR=""
for a in "${EXTRA_ARGS[@]}"; do
    EXTRA_ARGS_JOINED_STR+=" $(printf '%q' "$a")"
done

BOOTSTRAP_INJECTED="
export RUN_ID='${RUN_ID}'
export SPLIT='${SPLIT}'
export ADAPTER='${ADAPTER}'
export PYTHONUNBUFFERED=1
export HF_HOME=/workspace/.hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
rm -rf /workspace/models/recipes/dgx_spark/unsloth_compiled_cache/ 2>/dev/null || true
pip install --quiet transformers peft hf_transfer 'datasets==4.3.0' 'trl==0.26.1'
pip install --quiet --no-deps unsloth unsloth_zoo bitsandbytes
pip uninstall --quiet -y torchao || true
exec python /workspace/eval/run.py \\
    --run-id   '\${RUN_ID}' \\
    --split    /workspace/\${SPLIT} \\
    --adapter  /workspace/\${ADAPTER} \\
    ${EXTRA_ARGS_JOINED_STR}
"

echo "[run_in_container.sh] Launching ${EVAL_CONTAINER}"
echo "  repo   : ${REPO_ROOT} -> /workspace"
echo "  HF     : ${HF_CACHE_HOST} -> /workspace/.hf_cache"
echo "  run-id : ${RUN_ID}"
echo "  split  : ${SPLIT}"
echo "  adapter: ${ADAPTER}"
echo "  extra  : ${EXTRA_ARGS[*]:-<none>}"
echo ""

exec docker run --rm --name "${EVAL_CONTAINER}" \
    --gpus all \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --ipc=host \
    -v "${REPO_ROOT}:/workspace" \
    -v "${HF_CACHE_HOST}:/workspace/.hf_cache" \
    -w /workspace \
    "${IMAGE}" \
    bash -c "${BOOTSTRAP_INJECTED}"
