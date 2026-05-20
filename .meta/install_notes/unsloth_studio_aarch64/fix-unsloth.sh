#!/usr/bin/env bash
# Unsloth Studio aarch64 fix-up
#
# Run this AFTER `curl -fsSL https://unsloth.ai/install.sh | sh` fails at
# the "extras" / "extras-no-deps" step on a DGX Spark (or any aarch64 box).
# The official installer pins torchcodec==0.10.0 which has no aarch64 wheel;
# this script installs the remaining non-audio extras and the Studio backend
# deps that get skipped by the rollback.
#
# Idempotent: pip will no-op on packages already at the correct version.
# See README.md in this directory for full context.

set -euo pipefail

UNSLOTH_VENV="${UNSLOTH_VENV:-$HOME/.unsloth/studio/unsloth_studio}"
PIP="$UNSLOTH_VENV/bin/pip"

if [ ! -x "$PIP" ]; then
    echo "ERROR: pip not found at $PIP" >&2
    echo "Did you run the Unsloth installer first?" >&2
    echo "  curl -fsSL https://unsloth.ai/install.sh | sh" >&2
    echo "(It is expected to fail at 'extras'; come back and run this after.)" >&2
    exit 1
fi

echo "==> Using venv: $UNSLOTH_VENV"

# ── Step 1: extras-no-deps, minus the audio block ────────────────────────────
# Audio packages we INTENTIONALLY skip (require torchcodec==0.10.0 which has
# no aarch64 wheel): descript-audio-codec descript-audiotools julius
# torchcodec snac. If you later need them, see "Audio extras (optional)" in
# README.md.
#
# peft/trl pins matter: the installer's requirements file notes that
# peft 0.19+ "causes export subprocess shutdown issues in Studio".

echo "==> Installing non-audio extras (no-deps)"
"$PIP" install --no-deps --no-cache-dir \
    peft==0.18.1 \
    trl==0.23.1 \
    'git+https://github.com/meta-pytorch/OpenEnv.git' \
    torch-c-dlpack-ext \
    sentence_transformers==5.2.0 \
    transformers==4.57.6 \
    pytorch_tokenizers \
    kernels==0.12.1

# ── Step 2: Studio backend deps that the rollback skipped ────────────────────
# These come from studio/backend/requirements/studio.txt and extras.txt.
# Installed WITH deps because that is how the official installer handles them.

echo "==> Installing Studio backend deps (with deps)"
"$PIP" install --no-cache-dir \
    structlog \
    fastapi \
    diceware \
    ddgs \
    ruamel.yaml

# ── Smoke test ───────────────────────────────────────────────────────────────
echo "==> Smoke-testing imports"
"$UNSLOTH_VENV/bin/python" - <<'PY'
import unsloth, peft, trl, transformers, sentence_transformers, kernels
import structlog, fastapi
import torch
print(f"unsloth                {unsloth.__version__}")
print(f"torch                  {torch.__version__}  cuda={torch.cuda.is_available()}")
print(f"peft                   {peft.__version__}")
print(f"trl                    {trl.__version__}")
print(f"transformers           {transformers.__version__}")
print(f"sentence_transformers  {sentence_transformers.__version__}")
print(f"kernels                {kernels.__version__}")
print(f"structlog              {structlog.__version__}")
print(f"fastapi                {fastapi.__version__}")
PY

echo
echo "✅ Done. Launch Studio with one of:"
echo "   - Double-click the 'Unsloth Studio' desktop icon"
echo "   - $HOME/.local/share/unsloth/launch-studio.sh"
echo "   - unsloth studio   (then open http://localhost:8888)"
