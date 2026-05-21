"""Audit: how does original_template/ relate to python_scripts/?"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .code_base/
OT = ROOT / "original_template"
PS = ROOT / "python_scripts"

def norm(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")

identical = 0
near = 0  # < 5% byte diff
different = 0
diffs = []
for f in OT.iterdir():
    if not f.is_file():
        continue
    other = PS / f.name
    if not other.exists():
        continue
    a, b = norm(f), norm(other)
    if a == b:
        identical += 1
    else:
        ratio = abs(len(a) - len(b)) / max(len(a), len(b), 1)
        if ratio < 0.05:
            near += 1
        else:
            different += 1
        diffs.append((f.name, len(a), len(b), ratio))

print(f"Total compared: {identical + near + different}")
print(f"  Identical:     {identical}")
print(f"  Near (<5%):    {near}")
print(f"  Different:     {different}")
print()
diffs.sort(key=lambda x: -x[3])
print("Largest size deltas:")
for name, la, lb, r in diffs[:10]:
    print(f"  {name}: OT={la}B  PS={lb}B  delta={r:.1%}")
