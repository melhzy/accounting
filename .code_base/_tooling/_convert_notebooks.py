"""
One-shot script: convert all .ipynb under SRC to .py, and copy all .py under SRC,
mirroring the source directory layout into DST. Source layout is preserved to
avoid the 108 filename collisions across subfolders (e.g. nb/ vs python_scripts/).
"""
from __future__ import annotations

import shutil
import sys
import time
import traceback
from pathlib import Path

import nbformat
from nbconvert import PythonExporter

SRC = Path(r"D:\Github\notebooks")
DST = Path(r"D:\Github\accounting\code_base")

def convert_ipynb(src: Path, dst: Path, exporter: PythonExporter) -> None:
    nb = nbformat.read(src, as_version=4)
    body, _ = exporter.from_notebook_node(nb)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(body, encoding="utf-8")

def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    exporter = PythonExporter()

    ipynb_files = [p for p in SRC.rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts]
    py_files = list(SRC.rglob("*.py"))

    print(f"Source: {SRC}")
    print(f"Destination: {DST}")
    print(f".ipynb to convert: {len(ipynb_files)}")
    print(f".py to copy:       {len(py_files)}")
    print()

    converted = 0
    conv_failures: list[tuple[Path, str]] = []
    t0 = time.time()
    for i, src in enumerate(ipynb_files, 1):
        rel = src.relative_to(SRC).with_suffix(".py")
        dst = DST / rel
        try:
            convert_ipynb(src, dst, exporter)
            converted += 1
        except Exception as exc:  # noqa: BLE001
            conv_failures.append((src, f"{type(exc).__name__}: {exc}"))
        if i % 50 == 0 or i == len(ipynb_files):
            print(f"  [convert] {i}/{len(ipynb_files)}  ok={converted}  fail={len(conv_failures)}")

    copied = 0
    copy_failures: list[tuple[Path, str]] = []
    for i, src in enumerate(py_files, 1):
        rel = src.relative_to(SRC)
        dst = DST / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        except Exception as exc:  # noqa: BLE001
            copy_failures.append((src, f"{type(exc).__name__}: {exc}"))
        if i % 100 == 0 or i == len(py_files):
            print(f"  [copy]    {i}/{len(py_files)}  ok={copied}  fail={len(copy_failures)}")

    elapsed = time.time() - t0
    print()
    print(f"Done in {elapsed:.1f}s.")
    print(f"  converted: {converted}/{len(ipynb_files)}")
    print(f"  copied:    {copied}/{len(py_files)}")

    if conv_failures:
        print(f"\nConversion failures ({len(conv_failures)}):")
        for p, msg in conv_failures[:20]:
            print(f"  - {p}\n      {msg}")
        if len(conv_failures) > 20:
            print(f"  ... and {len(conv_failures) - 20} more")
    if copy_failures:
        print(f"\nCopy failures ({len(copy_failures)}):")
        for p, msg in copy_failures[:20]:
            print(f"  - {p}\n      {msg}")
        if len(copy_failures) > 20:
            print(f"  ... and {len(copy_failures) - 20} more")

    return 0 if not conv_failures and not copy_failures else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
