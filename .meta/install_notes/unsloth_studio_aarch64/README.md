# Unsloth Studio on NVIDIA DGX Spark (GB10 / aarch64)

> ⚠️ **Parallel install path — NOT the production training path.**
> For this repo (`accounting`), production training runs in the NGC
> container at `models/recipes/dgx_spark/`. These notes cover the
> standalone Unsloth Studio install (UI + GGUF chat + Studio-side
> fine-tuning) and are kept as alternative-recipe reference only.

Replicable install guide for getting **Unsloth Studio** running on an NVIDIA
DGX Spark workstation. The stock `unsloth.ai` installer fails on aarch64
because one of its pinned audio dependencies (`torchcodec==0.10.0`) has no
aarch64 wheel; this guide installs the core stack, then patches in the
remaining non-audio extras and Studio backend deps by hand, and builds
`llama-server` from `llama.cpp` so Studio can actually serve GGUF models.

If you do not need audio/video features (TTS, ASR, audio datasets) this
produces a fully working Studio install. If you DO need audio, see
[Audio extras (optional)](#audio-extras-optional) at the bottom.

---

## Verified environment

| Component | Value |
|---|---|
| Hardware | NVIDIA DGX Spark (GB10 Grace Blackwell superchip) |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) |
| Kernel | `6.14.0-1015-nvidia` aarch64 |
| GPU | NVIDIA GB10, CUDA compute capability **12.1** |
| NVIDIA driver | 580.95.05 |
| CUDA toolkit | 13.0 |
| Python in venv | 3.13.11 (auto-chosen by installer) |
| Unsloth Studio | 2026.5.5 |
| PyTorch | 2.10.0+cu130 |

Anything aarch64 + Ubuntu 24.04 + a Blackwell GPU should track this guide
closely; older Ampere/Hopper aarch64 boxes will work too but you can
optionally use a different PyTorch CUDA build.

---

## Prerequisites

1. **System packages** (Ubuntu 24.04 ships most of these; install anything
   missing):
   ```
   sudo apt update
   sudo apt install -y curl git unzip ffmpeg ca-certificates \
                       cmake ninja-build build-essential libcurl4-openssl-dev
   ```
   The last line covers the llama.cpp + `llama-server` build that Studio
   needs to serve GGUF models (Gemma 4, Qwen3 GGUFs, etc.).

2. **NVIDIA driver + CUDA**. DGX Spark systems ship pre-configured. Verify:
   ```
   nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv
   nvcc --version
   ```
   Driver 580+ and CUDA 13 are what we tested.

3. **Disk space**. The Unsloth venv is ~10 GB after install (PyTorch + CUDA
   libs dominate). Default location is `~/.unsloth/studio/unsloth_studio`.
   Override with `UNSLOTH_STUDIO_HOME=/some/path` if needed.

4. **No prior venv at the target path**. The installer creates its own
   Python 3.13 venv from scratch and will refuse / rollback if state is
   inconsistent. Clean install is easiest.

---

## Install

### Step 1 — Run the official installer (expect it to fail at "extras")

```
curl -fsSL https://unsloth.ai/install.sh | sh
```

It will get through:
- venv creation
- PyTorch (cu130)
- `unsloth` library
- `unsloth-zoo`
- frontend assets

…and then fail at **`deps [======--------------]  4/13  extra codecs`**
with:

```
× No solution found when resolving dependencies:
╰─▶ Because torchcodec==0.10.0 has no wheels with a matching platform tag
    (e.g., manylinux_2_39_aarch64) ...
```

The installer prints `restored previous environment after failed install`
at the end. **Do not panic** — most of the install survived; only the
"extras" and "extras-no-deps" steps did not run.

### Step 2 — Apply the aarch64 fix script

From the repo root:

```
bash .meta/install_notes/unsloth_studio_aarch64/complete-install.sh
```

(The script lives alongside this README. Safe to re-run — pip is a no-op
on packages already at the correct version.)

What it does:
1. **Skips the audio-only extras** (`descript-audio-codec`,
   `descript-audiotools`, `julius`, `torchcodec==0.10.0`, `snac`) — the
   `torchcodec` pin is what breaks aarch64.
2. **Installs the remaining `extras-no-deps` packages** with `--no-deps`,
   matching the installer's own pinning. Notably this **downgrades**
   `peft` (0.19.x → 0.18.1) and `trl` (0.24.x → 0.23.1); the Unsloth
   requirements file explicitly warns that peft 0.19+ "causes export
   subprocess shutdown issues in Studio".
3. **Installs the Studio backend deps** that were never run (`structlog`,
   `fastapi`, `diceware`, `ddgs`, `ruamel.yaml`).
4. **Builds llama.cpp's `llama-server` with CUDA** at
   `~/.unsloth/llama.cpp/build/bin/llama-server` so Studio can serve
   GGUF models. Auto-detects the GPU compute capability (GB10 → sm_121).
   Skipped on re-runs if the binary already exists.

   The script pins llama.cpp to a verified SHA
   (`ad277572619fcfb6ddd38f4c6437283a4b2b8636`, mid-May 2026) so
   upstream-master breakage cannot break the build. Bump by exporting
   `LLAMA_CPP_SHA=<new_sha>` before running the script.

5. **Splits the HuggingFace cache** by appending
   `export HF_HOME=~/.cache/huggingface-studio` to
   `~/.local/share/unsloth/studio.conf` (sourced by the launcher).
   Prevents the recurring "Permission denied on `~/.cache/huggingface/`"
   failure when something else on the host — most notably the NGC
   container at `models/recipes/dgx_spark/` — writes into the default
   HF cache as root. Studio gets its own cache; the container keeps the
   default; they never collide. Override with `HF_HOME_STUDIO=<path>`.

Total runtime: ~3–5 minutes on a DGX Spark (~2 min of that is the
llama.cpp build, single-shot — re-runs are instant).

> 💡 **Before re-running on an existing install:** kill any running
> Studio first (`pkill -f 'unsloth studio'` or close it from the
> system tray). The script does not stop Studio for you; running it
> against a live server is harmless but the new `llama-server` won't
> be picked up until Studio is restarted.

### Step 3 — Verify

```
/home/zi/.unsloth/studio/unsloth_studio/bin/python -c "
import unsloth, peft, trl, transformers, sentence_transformers, kernels, structlog, fastapi
import torch
print('unsloth', unsloth.__version__)
print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())
print('peft', peft.__version__, 'trl', trl.__version__)
"
```

You should see CUDA `True`, peft `0.18.1`, trl `0.23.1`, and no
ModuleNotFoundError.

### Step 4 — Launch Studio

Any of these work:

- **Desktop shortcut**: search "Unsloth Studio" in the GNOME activities /
  app launcher. Double-click. A terminal opens and your browser is taken
  to `http://localhost:8888`.

- **Launch script**: `/home/zi/.local/share/unsloth/launch-studio.sh`
  (auto-port-finds 8888 → 8908, polls health, opens browser).

- **Raw CLI**: `unsloth studio` and then open `http://localhost:8888`
  yourself. Useful for seeing log output directly.

---

## Known issues / caveats

### GB10 compute capability vs PyTorch ceiling

PyTorch 2.10.0+cu130 reports a max supported compute capability of
**12.0**, while DGX Spark's GB10 is **12.1**. You will see this warning
on every torch CUDA init:

```
Found GPU0 NVIDIA GB10 which is of cuda capability 12.1.
Minimum and Maximum cuda capability supported by this version of PyTorch is
(8.0) - (12.0)
```

In practice most operations work via JIT fallback. If you hit a
`no kernel image is available for execution on the device` or a PTX
error during model load, switch to a PyTorch nightly built for
Blackwell:

```
/home/zi/.unsloth/studio/unsloth_studio/bin/pip install --pre --upgrade \
  --index-url https://download.pytorch.org/whl/nightly/cu130 \
  torch torchvision torchaudio
```

### Re-running the installer wipes everything

`curl ... install.sh | sh` **recreates the venv from scratch** and
reinstalls the same broken pins. Don't re-run it casually. If you do,
re-run `complete-install.sh` immediately after.

This also applies to any in-app "update" that calls the installer under
the hood. Worth checking release notes before clicking update buttons.

### Desktop icon opens a terminal window that closes instantly

Symptom: double-clicking "Unsloth Studio" in the GNOME app launcher
pops a terminal that vanishes in under a second; the browser never
opens. This means the launcher invoked `unsloth studio` but the process
exited immediately, almost always due to a missing Python module in the
venv (we hit `ModuleNotFoundError: structlog` and similar during
bring-up). To diagnose, run it manually from a stable terminal:

```
unsloth studio
```

The traceback will tell you which import failed. If it's a Studio
backend dep, re-run `complete-install.sh` to top everything up.

### `openenv-core requires gradio`

You will see this warning during the fix script. It is harmless —
Unsloth's `extras.txt` deliberately comments out gradio because Studio's
UI is React + FastAPI, not Gradio. Studio doesn't import gradio.

### "Permission denied" on `~/.cache/huggingface/...` during training

Symptom (in the Studio UI):

```
Failed to check dataset format: [Errno 13] Permission denied:
'/home/zi/.cache/huggingface/datasets/json/default-XXXXXXXXXXX'
```

Root cause: another process — usually the NGC container at
`models/recipes/dgx_spark/`, but anything `sudo`-ed that uses
`huggingface_hub` qualifies — wrote into `~/.cache/huggingface/` as
root. Studio runs as your host user and can no longer create files
under those root-owned directories.

`complete-install.sh` now prevents this going forward by giving Studio
its own cache at `~/.cache/huggingface-studio` (see Step 2 bullet 5).
For the legacy mess that's already there, reclaim ownership once:

```
sudo chown -R $USER:$USER ~/.cache/huggingface
```

Long-term, to stop the container from creating root-owned files at
all, add `--user $(id -u):$(id -g)` to the `docker run` in Leo's
recipe — that's an orchestrator-level change, separate from these
install notes.

### Raw `unsloth studio` ignores Studio's HF cache

The HF_HOME split lives in `~/.local/share/unsloth/studio.conf`,
which is sourced only by the launcher (desktop icon /
`launch-studio.sh`). If you run `unsloth studio` directly from a
terminal, either prefix the command:

```
HF_HOME=~/.cache/huggingface-studio unsloth studio
```

…or add the export to your `~/.bashrc`. The launcher path is fine
either way.

### GGUF models fail with "llama-server binary not found"

If you ever see:

```
Invalid model: llama-server binary not found — cannot load GGUF models.
Run setup.sh to build it, or set LLAMA_SERVER_PATH.
```

the `complete-install.sh` step that builds llama.cpp didn't run, or the
binary was deleted. Studio looks for `llama-server` in this order:

1. `$LLAMA_SERVER_PATH` (direct path to a binary)
2. `$UNSLOTH_LLAMA_CPP_PATH/build/bin/llama-server` (custom dir)
3. `~/.unsloth/llama.cpp/build/bin/llama-server` ← **what we build**
4. `llama-server` on `PATH` (system install)

Re-run `complete-install.sh` to rebuild it. (There is no shipped
`setup.sh` despite what the error message says — that text predates the
pip-installed Studio.)

---

## Audio extras (optional)

If you later need TTS/ASR features, the audio block is recoverable on
aarch64 by bumping `torchcodec` (the 0.11+ line has aarch64 wheels):

```
/home/zi/.unsloth/studio/unsloth_studio/bin/pip install --no-deps --no-cache-dir \
  descript-audio-codec descript-audiotools julius snac \
  torchcodec==0.12.0
```

You may additionally need `mecab-python3` and `openai-whisper` for some
TTS pipelines (OuteTTS in particular). The installer's `extras.txt` lists
them under `MeCab` and `openai-whisper` respectively.

---

## File layout in this directory

```
README.md             this guide
complete-install.sh   idempotent script that runs Step 2 above
```

The install script is safe to re-run:
- pip is a no-op on packages already at the correct version,
- the llama.cpp clone is skipped if the directory already exists,
- the llama-server build is skipped if the binary is already present.
