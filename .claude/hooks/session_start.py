"""SessionStart hook for the Accounting LLM Framework.

Wired in .claude/settings.json (SessionStart matcher: startup + resume).

What it does on every session start:
    1. Print the "read first" pointers (.meta/ROADMAP.md + hardware.md row).
    2. Re-probe the host (regenerate .meta/host.json) and flag drift if
       OS family / CPU arch / GPU model / critical ML packages changed
       since the last probe.
    3. Print Diana's dataset anchor + run-id ledger so the session starts
       with the version pins in view.

Output goes to stdout (ASCII-only for Windows cp1252 compatibility).
Claude Code's harness surfaces it as session context. Never exits
non-zero (that would block session start); on any internal error,
prints a single warning line and continues.

The script is cross-platform (Windows / macOS / Linux). It deliberately
uses only stdlib --- no third-party deps at session start.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULE = "-" * 64


def _safe_read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _print_header() -> None:
    print(RULE)
    print("Accounting LLM Framework -- session start")
    print(RULE)


def _print_roadmap_pointer() -> None:
    roadmap = REPO / ".meta" / "ROADMAP.md"
    if roadmap.exists():
        print("[read first] .meta/ROADMAP.md (Pat's live verdicts + next steps)")
    else:
        print("[warn] .meta/ROADMAP.md missing -- Pat synthesis layer not present")


def _reprobe_host() -> dict | None:
    """Re-run probe_host.py; return parsed host.json or None on failure."""
    probe = REPO / ".meta" / "probe_host.py"
    host_json = REPO / ".meta" / "host.json"
    if not probe.exists():
        print("[warn] .meta/probe_host.py missing -- skipping host check")
        return _safe_read_json(host_json) if host_json.exists() else None
    try:
        subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(REPO),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except Exception as e:
        print(f"[warn] probe_host.py failed: {type(e).__name__} -- using last-known host.json")
    return _safe_read_json(host_json) if host_json.exists() else None


def _format_host_row(host: dict) -> str:
    """One-line summary of the current host. Defensive against schema shifts."""
    os_info = host.get("os") or {}
    os_family = os_info.get("system") or os_info.get("family") or "?"

    cpu_info = host.get("cpu") or {}
    cpu_arch = cpu_info.get("arch") or {}
    arch = cpu_arch.get("family") if isinstance(cpu_arch, dict) else cpu_arch
    arch = arch or "?"

    gpu_info = host.get("gpu")
    gpu = "?"
    if isinstance(gpu_info, list) and gpu_info:
        first = gpu_info[0]
        if isinstance(first, dict):
            gpu = first.get("name") or first.get("vendor") or "?"
    elif isinstance(gpu_info, dict):
        cuda = gpu_info.get("cuda") or {}
        devices = (cuda.get("devices") if isinstance(cuda, dict) else None) or []
        if devices and isinstance(devices[0], dict):
            gpu = devices[0].get("name", "?")
        mps = gpu_info.get("apple_mps") or {}
        if isinstance(mps, dict) and mps.get("available"):
            gpu = "Apple MPS"
    return f"{os_family} | {arch} | {gpu}"


def _print_host_summary(host: dict | None) -> None:
    if host is None:
        print("[warn] host.json unavailable -- cannot summarize current host")
        return
    print(f"[host] {_format_host_row(host)}")
    print("       Compare against .meta/hardware.md compatibility matrix.")
    print("       The ACTIVE-row pointer determines algorithm defaults.")


def _print_version_pins() -> None:
    """Surface the dataset anchor + run-id ledger from ROADMAP.md."""
    print("[pins] (see .meta/ROADMAP.md sec.1 for the bump policy)")
    print("       dataset  : spiceland9e-v1.1.0  (sha fed6eb17de8be1e4...)")
    print("       pipeline : pipeline-v0.3.0")
    print("       run id   : qwen3-4b-4bit-qlora-s00-r0  (ACTIVE row; executed)")


def _print_agent_dispatch_hint() -> None:
    print("[lenses] Dispatch by name via the Agent tool:")
    print("         Pat | Carla | Diana | Riley | Solomon | Vera | Edie | Leo")
    print("         Fan-out: dispatch in parallel; Pat closes.")
    print("         Roster: .claude/agents/README.md")


def _print_footer() -> None:
    print(RULE)


def main() -> int:
    try:
        _print_header()
        _print_roadmap_pointer()
        host = _reprobe_host()
        _print_host_summary(host)
        _print_version_pins()
        _print_agent_dispatch_hint()
        _print_footer()
    except Exception as e:
        print(f"[warn] session_start hook error: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
