#!/usr/bin/env bash
# Unsloth Studio aarch64 / DGX Spark complete install
#
# Run this AFTER `curl -fsSL https://unsloth.ai/install.sh | sh` fails at
# the "extras" / "extras-no-deps" step on a DGX Spark (or any aarch64 box).
# The official installer pins torchcodec==0.10.0 which has no aarch64 wheel;
# this script installs the remaining non-audio extras, the Studio backend
# deps that get skipped by the rollback, and builds llama.cpp's
# llama-server with CUDA so Studio can actually serve GGUF models.
#
# Idempotent: pip is a no-op on packages already at the correct version,
# and the llama.cpp build is skipped if the binary already exists.
# See README.md in this directory for full context.

set -euo pipefail

UNSLOTH_VENV="${UNSLOTH_VENV:-$HOME/.unsloth/studio/unsloth_studio}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$HOME/.unsloth/llama.cpp}"
LLAMA_SERVER_BIN="$LLAMA_CPP_DIR/build/bin/llama-server"
# Pinned SHA that we verified builds cleanly on DGX Spark (GB10 / CUDA 13.0)
# on 2026-05-20. Override with LLAMA_CPP_SHA=<sha> to bump.
LLAMA_CPP_SHA="${LLAMA_CPP_SHA:-ad277572619fcfb6ddd38f4c6437283a4b2b8636}"
PIP="$UNSLOTH_VENV/bin/pip"

if [ ! -x "$PIP" ]; then
    echo "ERROR: pip not found at $PIP" >&2
    echo "Did you run the Unsloth installer first?" >&2
    echo "  curl -fsSL https://unsloth.ai/install.sh | sh" >&2
    echo "(It is expected to fail at 'extras'; come back and run this after.)" >&2
    exit 1
fi

echo "==> Using venv:      $UNSLOTH_VENV"
echo "==> llama.cpp dir:   $LLAMA_CPP_DIR"

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

# ── Step 3: Build llama.cpp's llama-server with CUDA ─────────────────────────
# Studio looks for llama-server at ~/.unsloth/llama.cpp/build/bin/llama-server
# (override with LLAMA_SERVER_PATH or UNSLOTH_LLAMA_CPP_PATH env vars). Without
# it, GGUF model downloads fail with:
#   "llama-server binary not found — cannot load GGUF models."
#
# CMAKE_CUDA_ARCHITECTURES=native auto-detects the local GPU. On DGX Spark
# (GB10) this resolves to 121a-real (sm_121, the Grace Blackwell arch).

if [ -x "$LLAMA_SERVER_BIN" ]; then
    echo "==> llama-server already built: $LLAMA_SERVER_BIN  (skipping)"
else
    echo "==> Building llama.cpp + llama-server with CUDA"

    for tool in cmake ninja git nvcc g++; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            echo "ERROR: '$tool' not found on PATH. Install with:" >&2
            echo "  sudo apt install -y cmake ninja-build git build-essential libcurl4-openssl-dev" >&2
            echo "  (and CUDA toolkit 12+ for nvcc)" >&2
            exit 1
        fi
    done

    if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
        echo "  git clone https://github.com/ggml-org/llama.cpp.git"
        git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP_DIR"
    fi

    # Pin to the verified SHA. fetch-by-sha works against GitHub.
    current_sha="$(git -C "$LLAMA_CPP_DIR" rev-parse HEAD 2>/dev/null || true)"
    if [ "$current_sha" != "$LLAMA_CPP_SHA" ]; then
        echo "  pinning llama.cpp to $LLAMA_CPP_SHA"
        git -C "$LLAMA_CPP_DIR" fetch --quiet origin "$LLAMA_CPP_SHA" 2>/dev/null \
            || git -C "$LLAMA_CPP_DIR" fetch --quiet origin
        git -C "$LLAMA_CPP_DIR" checkout --quiet "$LLAMA_CPP_SHA"
    fi

    cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=ON \
        -DCMAKE_CUDA_ARCHITECTURES=native \
        -DLLAMA_CURL=ON

    cmake --build "$LLAMA_CPP_DIR/build" --config Release --target llama-server -j "$(nproc)"

    if [ ! -x "$LLAMA_SERVER_BIN" ]; then
        echo "ERROR: build finished but $LLAMA_SERVER_BIN is missing" >&2
        exit 1
    fi
fi

# ── Step 4: Studio-specific HF cache (avoid root-owned-files recurrence) ─────
# When another tool (NGC container, sudo'd training, etc.) writes into
# ~/.cache/huggingface as root, Studio (running as the host user) can no
# longer write there and dataset format checks fail with EACCES. We give
# Studio its own HF_HOME so it never collides with whatever the container
# writes. The launcher (~/.local/share/unsloth/launch-studio.sh) sources
# studio.conf, so an `export HF_HOME=...` there reaches the Studio process.
#
# Note: this only affects launches via the desktop icon or launch-studio.sh.
# If you run `unsloth studio` directly from a terminal, prefix it with
# `HF_HOME=~/.cache/huggingface-studio` or add the export to your shell rc.

HF_HOME_STUDIO="${HF_HOME_STUDIO:-$HOME/.cache/huggingface-studio}"
STUDIO_CONF="$HOME/.local/share/unsloth/studio.conf"
HF_MARKER="# unsloth-studio-aarch64: HF_HOME split (see install_notes)"

mkdir -p "$HF_HOME_STUDIO"

if [ -f "$STUDIO_CONF" ]; then
    if grep -qF "$HF_MARKER" "$STUDIO_CONF" 2>/dev/null; then
        echo "==> studio.conf already has HF_HOME split  (skipping)"
    else
        echo "==> Adding HF_HOME=$HF_HOME_STUDIO to $STUDIO_CONF"
        {
            echo ""
            echo "$HF_MARKER"
            echo "export HF_HOME='$HF_HOME_STUDIO'"
        } >> "$STUDIO_CONF"
    fi
else
    echo "WARNING: $STUDIO_CONF not found; cannot inject HF_HOME split." >&2
    echo "         (Re-run after launching Studio once, which creates it.)" >&2
fi

# Surface (but do not fix) any root-owned files in the default HF cache —
# those are the legacy mess from before this split; user must chown.
if find "$HOME/.cache/huggingface" -maxdepth 4 ! -user "$USER" -print -quit 2>/dev/null | grep -q .; then
    cat <<EOM

  ⚠️  Found root-owned files in ~/.cache/huggingface (likely from container runs).
      Studio's new HF_HOME ($HF_HOME_STUDIO) is unaffected, but the old cache
      is still partly inaccessible to you. To reclaim it, run:

          sudo chown -R \$USER:\$USER ~/.cache/huggingface

EOM
fi

# ── Smoke test ───────────────────────────────────────────────────────────────
echo "==> Smoke-testing imports + llama-server"
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
"$LLAMA_SERVER_BIN" --version 2>&1 | sed 's/^/  llama-server: /'

echo
echo "✅ Done. Launch Studio with one of:"
echo "   - Double-click the 'Unsloth Studio' desktop icon"
echo "   - $HOME/.local/share/unsloth/launch-studio.sh"
echo "   - HF_HOME=$HF_HOME_STUDIO unsloth studio"
echo
echo "   Studio's HF cache: $HF_HOME_STUDIO"
