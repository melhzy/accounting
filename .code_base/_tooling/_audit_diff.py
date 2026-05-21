"""Audit: where exactly do nb/ vs python_scripts/ pairs differ?"""
from __future__ import annotations
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .code_base/
NB = ROOT / "nb"
PS = ROOT / "python_scripts"

def normalize(p: Path) -> list[str]:
    text = p.read_text(encoding="utf-8", errors="replace")
    return text.replace("\r\n", "\n").splitlines()

names = sorted(p.name for p in NB.iterdir() if p.is_file())

# Categorize the difference types
identical = 0
trivial_diff = []  # < 5 diff lines
medium_diff = []   # 5-30
large_diff = []    # > 30

samples_shown = 0
for n in names:
    a = normalize(NB / n)
    b = normalize(PS / n)
    if a == b:
        identical += 1
        continue
    diff = list(difflib.unified_diff(a, b, lineterm=""))
    diff_lines = [l for l in diff if l.startswith(("+ ", "- ", "+", "-")) and not l.startswith(("+++", "---"))]
    n_diff = len(diff_lines)
    entry = (n, n_diff, len(a), len(b))
    if n_diff < 5:
        trivial_diff.append(entry)
    elif n_diff <= 30:
        medium_diff.append(entry)
    else:
        large_diff.append(entry)

    if samples_shown < 3 and n_diff > 5:
        print(f"\n=== SAMPLE DIFF: {n} (diff_lines={n_diff}, nb={len(a)}L, ps={len(b)}L) ===")
        for line in diff[:60]:
            print(line)
        samples_shown += 1

print(f"\n{'='*60}")
print(f"Total pairs:  {len(names)}")
print(f"Identical:    {identical}")
print(f"Trivial (<5): {len(trivial_diff)}")
print(f"Medium 5-30:  {len(medium_diff)}")
print(f"Large >30:    {len(large_diff)}")
print()
if trivial_diff[:5]:
    print("Trivial examples:")
    for n, d, la, lb in trivial_diff[:5]:
        print(f"  {n}: {d} diff lines ({la}L vs {lb}L)")
if medium_diff[:5]:
    print("Medium examples:")
    for n, d, la, lb in medium_diff[:5]:
        print(f"  {n}: {d} diff lines ({la}L vs {lb}L)")
if large_diff[:5]:
    print("Large examples:")
    for n, d, la, lb in large_diff[:5]:
        print(f"  {n}: {d} diff lines ({la}L vs {lb}L)")
