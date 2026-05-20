"""Cross-platform host probe for the Accounting LLM Framework.

Run this at the start of every session — Pat reads the output as the
canonical "what OS + hardware are we on right now" record:

    python .meta/probe_host.py

Outputs:
    .meta/host.json    machine-readable; Pat reads this at session-start
                       to compare against .meta/hardware.md and flag drift
                       if the user moved the repo to a different OS or box.

Supports Windows, macOS (incl. Apple Silicon), and Linux. Uses stdlib
where possible, with fallbacks to vendor CLIs (nvidia-smi, sysctl, etc.).
Never raises on a missing tool — every probe returns a best-effort dict
with explanatory `note` fields.

The probe records ONLY what the current Python interpreter can see. If
you have multiple envs (system + conda), run the probe inside whichever
env will actually drive training/inference.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUT_PATH = Path(__file__).resolve().parent / "host.json"
ML_PACKAGES = [
    "torch", "unsloth", "transformers", "peft", "trl", "bitsandbytes",
    "accelerate", "datasets", "vllm", "tiktoken", "seedhash",
    "openpyxl", "docx", "xformers", "psutil",
]


def _run(cmd: list[str], timeout: int = 10) -> str | None:
    """Run a subprocess and return stdout. None on any failure."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            shell=False, check=False,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


# ============================================================================
# CPU architecture normalization
# ============================================================================

# Maps OS-specific platform.machine() returns into a canonical family + bits.
# Same ISA shows up as different strings depending on OS:
#   "AMD64" (Windows) == "x86_64" (Linux/macOS) → both x86-64
#   "arm64" (macOS) == "aarch64" (Linux)         → both ARMv8 64-bit
_ARCH_MAP = {
    "x86_64":  ("x86_64", 64),
    "amd64":   ("x86_64", 64),
    "x64":     ("x86_64", 64),
    "i386":    ("x86",    32),
    "i486":    ("x86",    32),
    "i586":    ("x86",    32),
    "i686":    ("x86",    32),
    "x86":     ("x86",    32),
    "arm64":   ("arm64",  64),
    "aarch64": ("arm64",  64),
    "armv8":   ("arm64",  64),
    "armv7l":  ("armv7",  32),
    "armv7":   ("armv7",  32),
    "arm":     ("armv7",  32),
}


def normalize_arch(raw: str) -> dict[str, Any]:
    raw_lc = (raw or "").lower()
    family, bits = _ARCH_MAP.get(raw_lc, (raw, None))
    return {
        "raw": raw,                      # exact platform.machine() return
        "family": family,                # canonical: x86_64 | arm64 | x86 | armv7
        "bits": bits,                    # 32 or 64
        # Python's own bitness can differ from CPU bitness (rare: 32-bit Python
        # on a 64-bit OS). Capture both so we never confuse the two.
        "python_bits": int(platform.architecture()[0].replace("bit", "")),
    }


# ============================================================================
# OS
# ============================================================================

def probe_os() -> dict[str, Any]:
    sysname = platform.system()  # "Windows" | "Darwin" | "Linux"
    info: dict[str, Any] = {
        "system": sysname,
        "platform": platform.platform(),
        "arch": normalize_arch(platform.machine()),
        "release": platform.release(),
    }
    if sysname == "Darwin":
        prod = _run(["sw_vers", "-productVersion"])
        if prod:
            info["macos_version"] = prod.strip()
        info["apple_silicon"] = info["arch"]["family"] == "arm64"
    elif sysname == "Linux":
        try:
            with open("/etc/os-release", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            info["distro"] = next((ln.split("=", 1)[1].strip('"')
                                   for ln in lines if ln.startswith("PRETTY_NAME=")), None)
        except OSError:
            info["distro"] = None
    elif sysname == "Windows":
        info["build"] = platform.version()  # e.g. "10.0.26200"
    return info


# ============================================================================
# Python + ML stack
# ============================================================================

def probe_python() -> dict[str, Any]:
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "in_conda_env": bool(os.environ.get("CONDA_PREFIX")),
        "conda_env_name": os.environ.get("CONDA_DEFAULT_ENV"),
    }


def probe_ml_packages() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in ML_PACKAGES:
        try:
            m = __import__(name)
            out[name] = getattr(m, "__version__", "installed")
        except ImportError:
            out[name] = None
        except Exception as e:
            out[name] = f"ERROR: {type(e).__name__}"
    return out


# ============================================================================
# CPU
# ============================================================================

def _normalize_vendor(s: str | None) -> str | None:
    """Map raw vendor string from OS probes to a canonical label.
    Intel/AMD/Apple/ARM-Ltd are the ones that actually drive algorithm choice."""
    if not s:
        return None
    sl = s.lower()
    if "intel" in sl or "genuineintel" in sl:
        return "intel"
    if "amd" in sl or "authenticamd" in sl:
        return "amd"
    if "apple" in sl:
        return "apple"
    if "arm" in sl:
        return "arm"
    return s


def probe_cpu() -> dict[str, Any]:
    sysname = platform.system()
    info: dict[str, Any] = {
        "arch": normalize_arch(platform.machine()),
        "logical_count": os.cpu_count(),
        "model": None,
        "vendor": None,
        "physical_count": None,
        "max_clock_mhz": None,
    }
    if sysname == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Processor | Select-Object "
                    "Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,Architecture | "
                    "ConvertTo-Json -Compress"])
        if out:
            try:
                d = json.loads(out)
                if isinstance(d, list):
                    d = d[0]
                info["model"] = d.get("Name", "").strip() or None
                info["vendor"] = _normalize_vendor(d.get("Manufacturer"))
                info["physical_count"] = d.get("NumberOfCores")
                info["logical_count"] = d.get("NumberOfLogicalProcessors") or info["logical_count"]
                info["max_clock_mhz"] = d.get("MaxClockSpeed")
                # Win32_Processor.Architecture: 0=x86, 5=ARM, 6=Itanium, 9=x64, 12=ARM64
                arch_code = d.get("Architecture")
                info["wmi_arch_code"] = arch_code
            except (json.JSONDecodeError, IndexError):
                pass
    elif sysname == "Darwin":
        for attr, key in [
            ("machdep.cpu.brand_string", "model"),
            ("machdep.cpu.vendor", "_vendor_raw"),
            ("hw.physicalcpu", "physical_count"),
            ("hw.logicalcpu", "logical_count"),
            ("hw.cpufrequency_max", "_max_clock_hz"),
        ]:
            out = _run(["sysctl", "-n", attr])
            if out:
                v = out.strip()
                if key == "_max_clock_hz":
                    try:
                        info["max_clock_mhz"] = int(v) // 1_000_000
                    except ValueError:
                        pass
                elif key == "_vendor_raw":
                    info["vendor"] = _normalize_vendor(v)
                else:
                    try:
                        info[key] = int(v)
                    except ValueError:
                        info[key] = v
        # Apple Silicon: machdep.cpu.vendor is empty on M-series, infer from arch
        if not info["vendor"] and info["arch"]["family"] == "arm64":
            info["vendor"] = "apple"
    elif sysname == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            for ln in lines:
                if ln.startswith("model name") and not info["model"]:
                    info["model"] = ln.split(":", 1)[1].strip()
                if ln.startswith("vendor_id") and not info["vendor"]:
                    info["vendor"] = _normalize_vendor(ln.split(":", 1)[1].strip())
                if ln.startswith("cpu cores") and not info["physical_count"]:
                    try:
                        info["physical_count"] = int(ln.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                if ln.startswith("cpu MHz") and not info["max_clock_mhz"]:
                    try:
                        info["max_clock_mhz"] = int(float(ln.split(":", 1)[1].strip()))
                    except ValueError:
                        pass
                # ARM Linux: vendor_id is absent; "CPU implementer" gives a hex code.
                if ln.startswith("CPU implementer") and not info["vendor"]:
                    code = ln.split(":", 1)[1].strip().lower()
                    arm_implementers = {
                        "0x41": "arm",       # ARM Ltd
                        "0x42": "broadcom",
                        "0x43": "cavium",
                        "0x4e": "nvidia",
                        "0x50": "amcc",
                        "0x51": "qualcomm",
                        "0x53": "samsung",
                        "0x56": "marvell",
                        "0x61": "apple",
                        "0x69": "intel",
                    }
                    info["vendor"] = arm_implementers.get(code, code)
        except OSError:
            pass
    return info


# ============================================================================
# RAM
# ============================================================================

def probe_ram() -> dict[str, Any]:
    sysname = platform.system()
    info: dict[str, Any] = {"total_gb": None, "available_gb": None}
    # psutil if available — most accurate cross-platform
    try:
        import psutil  # type: ignore
        v = psutil.virtual_memory()
        info["total_gb"] = round(v.total / 1024**3, 1)
        info["available_gb"] = round(v.available / 1024**3, 1)
        return info
    except ImportError:
        pass
    # Fallbacks
    if sysname == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "$o=Get-CimInstance Win32_OperatingSystem; "
                    "[pscustomobject]@{Total=$o.TotalVisibleMemorySize;Free=$o.FreePhysicalMemory} | "
                    "ConvertTo-Json -Compress"])
        if out:
            try:
                d = json.loads(out)
                info["total_gb"] = round(d["Total"] / 1024**2, 1)  # KB → GB
                info["available_gb"] = round(d["Free"] / 1024**2, 1)
            except (json.JSONDecodeError, KeyError):
                pass
    elif sysname == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out:
            try:
                info["total_gb"] = round(int(out.strip()) / 1024**3, 1)
            except ValueError:
                pass
    elif sysname == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                m = {ln.split(":", 1)[0]: ln.split(":", 1)[1].strip()
                     for ln in fh.read().splitlines() if ":" in ln}
            if "MemTotal" in m:
                info["total_gb"] = round(int(m["MemTotal"].split()[0]) / 1024**2, 1)
            if "MemAvailable" in m:
                info["available_gb"] = round(int(m["MemAvailable"].split()[0]) / 1024**2, 1)
        except OSError:
            pass
    return info


# ============================================================================
# GPU
# ============================================================================

def probe_gpu() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    # 1) torch.cuda (NVIDIA on Win/Linux, ROCm on Linux for AMD)
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                p = torch.cuda.get_device_properties(i)
                gpus.append({
                    "vendor": "nvidia" if "NVIDIA" in p.name else "amd-rocm",
                    "name": p.name,
                    "vram_gb": round(p.total_memory / 1024**3, 1),
                    "compute_capability": f"{p.major}.{p.minor}",
                    "multi_processor_count": p.multi_processor_count,
                    "source": "torch.cuda",
                })
        # Apple Silicon MPS
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            gpus.append({
                "vendor": "apple",
                "name": "Apple Silicon GPU (MPS)",
                "vram_gb": None,  # unified memory — no separate VRAM number
                "source": "torch.mps",
                "note": "unified memory architecture; budget against RAM not VRAM",
            })
    except ImportError:
        pass
    # 2) nvidia-smi (richer info for NVIDIA, gives driver + free memory)
    nvsmi = _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free,compute_cap",
                  "--format=csv,noheader,nounits"])
    if nvsmi:
        for line in nvsmi.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                # Try to merge into the existing torch.cuda entry rather than duplicate
                match = next((g for g in gpus if g.get("name", "").startswith(parts[0][:20])), None)
                target = match or {"vendor": "nvidia", "name": parts[0],
                                   "vram_gb": round(int(parts[2]) / 1024, 1)
                                              if parts[2].isdigit() else None,
                                   "source": "nvidia-smi"}
                target["driver"] = parts[1]
                try:
                    target["vram_free_gb"] = round(int(parts[3]) / 1024, 1)
                except ValueError:
                    pass
                target["compute_capability"] = parts[4]
                if match is None:
                    gpus.append(target)
    # 3) Apple Silicon richer info via system_profiler
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        out = _run(["system_profiler", "SPHardwareDataType"])
        if out:
            for ln in out.splitlines():
                if "Chip:" in ln:
                    chip = ln.split(":", 1)[1].strip()
                    for g in gpus:
                        if g.get("vendor") == "apple":
                            g["name"] = chip + " GPU"
                            break
                    else:
                        gpus.append({"vendor": "apple", "name": chip + " GPU",
                                     "source": "system_profiler",
                                     "note": "unified memory; no torch.mps detection"})
                    break
    if not gpus:
        gpus.append({"vendor": "none", "name": None,
                     "note": "no GPU detected by torch/nvidia-smi/system_profiler"})
    return gpus


# ============================================================================
# Storage
# ============================================================================

def probe_storage() -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    sysname = platform.system()
    if sysname == "Windows":
        # Iterate over Windows drive letters
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if Path(drive).exists():
                try:
                    u = shutil.disk_usage(drive)
                    mounts.append({
                        "mount": f"{letter}:",
                        "total_gb": round(u.total / 1024**3, 1),
                        "free_gb": round(u.free / 1024**3, 1),
                        "pct_free": round(100 * u.free / u.total, 1) if u.total else None,
                    })
                except (OSError, PermissionError):
                    pass
    else:
        # macOS + Linux: probe a useful set of mountpoints
        candidates = ["/", str(Path.home())]
        if sysname == "Linux":
            candidates += ["/home", "/data", "/mnt", "/tmp"]
        elif sysname == "Darwin":
            candidates += ["/Volumes", "/System/Volumes/Data"]
        seen: set[str] = set()
        for c in candidates:
            try:
                rp = str(Path(c).resolve())
                if rp in seen or not Path(c).exists():
                    continue
                seen.add(rp)
                u = shutil.disk_usage(c)
                mounts.append({
                    "mount": c,
                    "total_gb": round(u.total / 1024**3, 1),
                    "free_gb": round(u.free / 1024**3, 1),
                    "pct_free": round(100 * u.free / u.total, 1) if u.total else None,
                })
            except (OSError, PermissionError):
                pass
    # Always include the repo root
    repo_root = Path(__file__).resolve().parents[1]
    try:
        u = shutil.disk_usage(repo_root)
        mounts.append({
            "mount": f"<repo_root: {repo_root}>",
            "total_gb": round(u.total / 1024**3, 1),
            "free_gb": round(u.free / 1024**3, 1),
            "pct_free": round(100 * u.free / u.total, 1) if u.total else None,
        })
    except OSError:
        pass
    return mounts


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    host = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "os": probe_os(),
        "python": probe_python(),
        "cpu": probe_cpu(),
        "ram": probe_ram(),
        "gpu": probe_gpu(),
        "storage": probe_storage(),
        "ml_stack": probe_ml_packages(),
        "probe_run_from": {
            "cwd": str(Path.cwd()),
            "script": str(Path(__file__).resolve()),
        },
    }

    OUT_PATH.write_text(json.dumps(host, indent=2, ensure_ascii=False), encoding="utf-8")

    # Human-readable summary to stdout
    os_info = host["os"]
    arch = os_info["arch"]
    arch_label = f"{arch['family']} {arch['bits']}-bit" if arch["bits"] else arch["family"]
    py_bits = arch["python_bits"]
    bit_warn = "  ⚠ 32-bit Python on 64-bit OS" if arch["bits"] == 64 and py_bits == 32 else ""
    print(f"OS          : {os_info['system']} ({os_info['platform']})")
    print(f"Arch        : {arch_label}   raw={arch['raw']!r}   Python={py_bits}-bit{bit_warn}")
    print(f"Python      : {host['python']['version']}  "
          f"({host['python']['conda_env_name'] or 'no conda env'})")
    cpu = host["cpu"]
    print(f"CPU         : {cpu.get('model') or 'unknown'}  "
          f"[{cpu.get('vendor') or 'vendor?'}]  "
          f"({cpu.get('physical_count') or '?'}c / {cpu.get('logical_count') or '?'}t)")
    ram = host["ram"]
    print(f"RAM         : {ram.get('total_gb') or '?'} GB total, "
          f"{ram.get('available_gb') or '?'} GB available")
    for g in host["gpu"]:
        vram = f", {g['vram_gb']} GB VRAM" if g.get("vram_gb") else ""
        print(f"GPU         : [{g.get('vendor')}] {g.get('name')}{vram}")
    for s in host["storage"]:
        print(f"Storage     : {s['mount']:<35s}  "
              f"{s['free_gb']} / {s['total_gb']} GB free  ({s.get('pct_free')}%)")
    stack_present = {k: v for k, v in host["ml_stack"].items() if v is not None}
    print(f"ML stack    : {len(stack_present)}/{len(host['ml_stack'])} packages present"
          f" ({', '.join(sorted(stack_present.keys()))})")
    print()
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
