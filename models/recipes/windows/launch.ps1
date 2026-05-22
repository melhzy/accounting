# Windows + RTX 4090 Laptop — launch JupyterLab in the `unsloth` conda env
# from the repo root, listening on 127.0.0.1:8888 (no token, no LAN exposure).
#
# This is the Windows-host analogue of `models/recipes/dgx_spark/launch.sh`.
# No container — the Windows row uses a native conda env (`.meta/hardware.md`
# "Dormant host details — Windows + RTX 4090 Laptop").
#
# Run:    powershell -ExecutionPolicy Bypass -File models\recipes\windows\launch.ps1
# Stop:   Ctrl-C in this terminal.

$ErrorActionPreference = 'Stop'

# -- paths (host) -------------------------------------------------------------
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$EnvName = 'unsloth'
$JupyterPort = if ($env:JUPYTER_PORT) { $env:JUPYTER_PORT } else { '8888' }

Write-Host "Repo root  : $RepoRoot"
Write-Host "Conda env  : $EnvName"
Write-Host "Port       : 127.0.0.1:$JupyterPort"
Write-Host ""

# -- locate conda -------------------------------------------------------------
$conda = (Get-Command conda -ErrorAction SilentlyContinue)
if (-not $conda) {
    throw "conda is not on PATH. Install Miniconda/Anaconda or `conda init powershell` first."
}

# -- verify env exists --------------------------------------------------------
$envList = & conda env list 2>$null | Out-String
if ($envList -notmatch "(?m)^\s*$([regex]::Escape($EnvName))\s") {
    throw "conda env '$EnvName' not found. Create it per .meta/hardware.md (Python 3.12, torch 2.8.0+cu126, Unsloth)."
}

# -- pre-flight: CUDA visible, vLLM absent ------------------------------------
# vLLM on Windows ships no `vllm._C` and unsloth_zoo imports it unconditionally,
# so its mere installation breaks `import unsloth`. Catch this here, not at the
# first training cell.
$preflight = @'
import importlib.util, sys
import torch
assert torch.cuda.is_available(), "torch.cuda.is_available() is False"
p = torch.cuda.get_device_properties(0)
print(f"torch     : {torch.__version__}")
print(f"gpu       : {p.name} ({p.total_memory/1024**3:.1f} GB, sm_{p.major}{p.minor})")
assert importlib.util.find_spec("vllm") is None, (
    "vllm is installed and will break `import unsloth` on Windows. "
    "Run: pip uninstall vllm -y"
)
print("vllm      : absent (good)")
'@

Write-Host "Pre-flight..."
$preflight | & conda run -n $EnvName --no-capture-output python -
if ($LASTEXITCODE -ne 0) { throw "Pre-flight failed (see error above)." }
Write-Host ""

# -- HF cache: pin to D: if not already set -----------------------------------
if (-not $env:HF_HOME) {
    $env:HF_HOME = 'D:\hf_cache'
    Write-Host "HF_HOME    : $env:HF_HOME (set by launcher — D: has more free space)"
} else {
    Write-Host "HF_HOME    : $env:HF_HOME (inherited from environment)"
}
$env:HF_HUB_ENABLE_HF_TRANSFER = '1'

# -- launch JupyterLab --------------------------------------------------------
Write-Host ""
Write-Host "Connect:"
Write-Host "  Browser  : http://127.0.0.1:$JupyterPort/lab"
Write-Host "  VS Code  : Ctrl-Shift-P -> 'Jupyter: Specify Jupyter Server' ->"
Write-Host "             http://127.0.0.1:$JupyterPort/?token=  (empty token)"
Write-Host "             then open models\recipes\windows\qwen3_4b_seed00_bf16_lora.ipynb"
Write-Host ""

Set-Location $RepoRoot
& conda run -n $EnvName --no-capture-output `
    jupyter lab `
        --no-browser `
        --ip=127.0.0.1 `
        --port=$JupyterPort `
        --ServerApp.token='' `
        --ServerApp.password='' `
        --ServerApp.root_dir="$RepoRoot"
