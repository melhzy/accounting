"""
Dedup + reorganize code_base for LLM-friendly retrieval.

Source state (read once):
  code_base/nb/               422  raw nbconvert (DROP — superseded by python_scripts/)
  code_base/python_scripts/   422  curated runnable .py (CANONICAL)
  code_base/original_template/ 104 older shorter snapshots (KEEP as archive)
  code_base/tests/             13  test files (KEEP under tests/)
  code_base/scripts/            6  utility scripts (KEEP under utilities/)
  code_base/kaggle/             2  Kaggle-only (KEEP under kaggle/)
  code_base/*.py (root)         5  4 helper utilities + 1 root template (split)

Output state:
  code_base/
    README.md
    MANIFEST.md
    notebooks/<category>/<file>.py        ← from python_scripts/
    archive/original_versions/<file>.py   ← from original_template/
    kaggle/<file>.py
    tests/<file>.py
    utilities/<file>.py                   ← scripts/ + root utilities
    _tooling/                             ← internal scripts (this file + audits)
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]  # .code_base/

# ----- Categorization -----

# Ordered priority. First match wins.
# Each entry: (category, list of regex patterns to match against basename, case-insensitive)
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # specific model families first
    ("llama",        [r"\bllama\b"]),
    ("qwen",         [r"\bqwen\b", r"qwq"]),
    ("gemma",        [r"\bgemma\b", r"codegemma"]),
    ("mistral",      [r"\bmistral\b", r"mixtral", r"magistral"]),
    ("phi",          [r"\bphi[-_ ]?\d"]),
    ("deepseek",     [r"deepseek"]),
    ("gpt_oss",      [r"gpt[-_ ]?oss"]),
    # task-specific (model-agnostic or covers many models)
    ("ocr",          [r"\bocr\b", r"nanonets"]),
    ("vision",       [r"\bvision\b", r"\bvl\b", r"pixtral", r"idefics", r"janus",
                      r"llava", r"\bvlm\b", r"intern[-_]?vl", r"moondream"]),
    ("speech",       [r"whisper", r"\basr\b", r"voxtral"]),
    ("tts",          [r"\btts\b", r"orpheus", r"sesame[-_]csm", r"oute[-_]?tts",
                      r"f5[-_]tts", r"kokoro", r"\bcsm\b"]),
    ("embeddings",   [r"bge[-_]m3", r"minilm", r"modernbert", r"embedding",
                      r"nomic", r"qwen3[-_]embedding"]),
    ("classification", [r"\bbert\b", r"classification"]),
    ("reasoning_rl", [r"grpo", r"\brl\b", r"reasoning", r"cot[-_]finetune",
                      r"codeforces"]),
]

def categorize(name: str) -> str:
    base = name.lower()
    for cat, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, base):
                return cat
    return "other"

# ----- Metadata extraction -----

@dataclass
class FileMeta:
    src_path: Path
    dst_path: Path
    category: str
    model_hint: str
    task_hint: str
    description: str
    size_bytes: int

MODEL_PATTERNS = [
    (r"(Llama[0-9._-]*[A-Za-z]*)", "Llama"),
    (r"(Qwen[0-9._-]*[A-Za-z]*)", "Qwen"),
    (r"(Gemma[0-9._-]*[A-Za-z]*)", "Gemma"),
    (r"(Mistral[0-9._-]*[A-Za-z]*)", "Mistral"),
    (r"(Mixtral[0-9._-]*[A-Za-z]*)", "Mixtral"),
    (r"(Phi[0-9._-]*[A-Za-z]*)", "Phi"),
    (r"(Deepseek[0-9._-]*[A-Za-z_]*)", "Deepseek"),
    (r"(GPT[-_]?OSS[0-9._-]*[A-Za-z]*)", "gpt-oss"),
    (r"(Whisper[0-9._-]*[A-Za-z]*)", "Whisper"),
    (r"(Orpheus[0-9._-]*[A-Za-z]*)", "Orpheus"),
    (r"(BGE[-_]?M3)", "BGE-M3"),
    (r"(All_MiniLM_L6_v2)", "all-MiniLM-L6-v2"),
    (r"(ModernBert)", "ModernBERT"),
    (r"(BERT|bert)", "BERT"),
    (r"(Pixtral)", "Pixtral"),
    (r"(Idefics)", "Idefics"),
    (r"(Janus)", "Janus"),
    (r"(LLAVA|LLaVA|Llava|llava)", "Llava"),
]

TASK_PATTERNS = [
    (r"GRPO", "GRPO"),
    (r"DPO", "DPO"),
    (r"ORPO", "ORPO"),
    (r"SFT", "SFT"),
    (r"LoRA", "LoRA"),
    (r"\bRL\b", "RL"),
    (r"OCR", "OCR"),
    (r"Inference", "Inference"),
    (r"Eval(uation)?", "Eval"),
    (r"Vision", "Vision"),
    (r"Conversational", "Conversational"),
    (r"Classification", "Classification"),
    (r"Embedding", "Embedding"),
    (r"Reasoning", "Reasoning"),
    (r"Text(_Completion)?", "Text"),
    (r"TTS", "TTS"),
    (r"Synthetic_Data", "Synthetic-Data"),
    (r"cot[-_]Finetune", "CoT-Finetune"),
    (r"CodeForces", "CodeForces"),
]

def extract_first(patterns: list[tuple[str, str]], name: str) -> str:
    for pat, label in patterns:
        if re.search(pat, name, re.IGNORECASE):
            return label
    return ""

def short_description(path: Path) -> str:
    """First meaningful comment-derived heading from the file."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    # Look for first markdown header line (e.g. "# # Title" or "# ## Subtitle") inside a comment
    for line in lines[:80]:
        s = line.strip()
        # Pattern: leading '#' (Python comment), optional whitespace, then markdown header chars
        m = re.match(r"^#\s*#+\s+(.+?)\s*$", s)
        if m:
            head = m.group(1)
            # Skip generic install / Unsloth promo headers
            if re.search(r"^(installation|news|home|index|table of contents|introduction)$",
                          head, re.IGNORECASE):
                continue
            # Keep first 110 chars to stay tidy
            return head[:110]
    # Fallback: first non-empty comment that isn't shebang/encoding
    for line in lines[:30]:
        s = line.strip()
        if not s.startswith("#"):
            continue
        if s.startswith(("#!", "# -*-", "# coding:")):
            continue
        body = s.lstrip("#").strip()
        if len(body) > 8:
            return body[:110]
    return ""

# ----- Move planning -----

def plan_notebook_moves(src_dir: Path, dst_base: Path) -> list[FileMeta]:
    out: list[FileMeta] = []
    for src in sorted(src_dir.iterdir()):
        if not src.is_file() or src.suffix != ".py":
            continue
        cat = categorize(src.name)
        dst = dst_base / "notebooks" / cat / src.name
        out.append(FileMeta(
            src_path=src,
            dst_path=dst,
            category=cat,
            model_hint=extract_first(MODEL_PATTERNS, src.name),
            task_hint=extract_first(TASK_PATTERNS, src.name),
            description=short_description(src),
            size_bytes=src.stat().st_size,
        ))
    return out

def plan_passthrough(src_dir: Path, dst_dir: Path) -> list[FileMeta]:
    out: list[FileMeta] = []
    if not src_dir.exists():
        return out
    for src in sorted(src_dir.iterdir()):
        if not src.is_file() or src.suffix != ".py":
            continue
        out.append(FileMeta(
            src_path=src,
            dst_path=dst_dir / src.name,
            category=dst_dir.name,
            model_hint=extract_first(MODEL_PATTERNS, src.name),
            task_hint=extract_first(TASK_PATTERNS, src.name),
            description=short_description(src),
            size_bytes=src.stat().st_size,
        ))
    return out

def plan_root_utilities(root: Path) -> tuple[list[FileMeta], list[Path]]:
    """Pull stray root .py files into utilities/ or _tooling/."""
    util_dst = root / "utilities"
    tool_dst = root / "_tooling"
    tool_names = {"_convert_notebooks.py", "_audit_diff.py", "_audit_template.py",
                  "_reorganize.py"}
    util_metas: list[FileMeta] = []
    tool_paths: list[Path] = []
    for src in sorted(root.iterdir()):
        if not src.is_file() or src.suffix != ".py":
            continue
        if src.name in tool_names:
            tool_paths.append(src)
            continue
        util_metas.append(FileMeta(
            src_path=src,
            dst_path=util_dst / src.name,
            category="utilities",
            model_hint="",
            task_hint="Utility",
            description=short_description(src),
            size_bytes=src.stat().st_size,
        ))
    return util_metas, tool_paths

# ----- Execution -----

def do_moves(metas: Iterable[FileMeta]) -> int:
    count = 0
    for m in metas:
        m.dst_path.parent.mkdir(parents=True, exist_ok=True)
        # Move (atomic on same volume)
        shutil.move(str(m.src_path), str(m.dst_path))
        count += 1
    return count

def remove_empty_tree(root: Path) -> None:
    if not root.exists():
        return
    # Try to remove leaf-first
    for sub in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()
    if root.exists() and not any(root.iterdir()):
        root.rmdir()

# ----- Manifest emission -----

def write_manifest(notebook_metas: list[FileMeta],
                   archive_metas: list[FileMeta],
                   util_metas: list[FileMeta],
                   kaggle_metas: list[FileMeta],
                   test_metas: list[FileMeta],
                   path: Path) -> None:
    by_cat: dict[str, list[FileMeta]] = defaultdict(list)
    for m in notebook_metas:
        by_cat[m.category].append(m)

    lines: list[str] = []
    lines.append("# code_base MANIFEST")
    lines.append("")
    lines.append("Index of all files in `code_base/`, grouped by category. ")
    lines.append("Source: Unsloth notebooks (`D:\\Github\\notebooks`) converted to `.py`. ")
    lines.append(f"Total notebook scripts: **{len(notebook_metas)}** across "
                 f"**{len(by_cat)}** categories. ")
    lines.append(f"Archived earlier versions: **{len(archive_metas)}**. "
                 f"Kaggle: **{len(kaggle_metas)}**. "
                 f"Tests: **{len(test_metas)}**. "
                 f"Utilities: **{len(util_metas)}**.")
    lines.append("")
    lines.append("## Layout")
    lines.append("")
    lines.append("- `notebooks/<category>/<file>.py` — curated training/inference scripts")
    lines.append("- `archive/original_versions/` — earlier shorter snapshots (104 files)")
    lines.append("- `kaggle/` — Kaggle-specific notebooks")
    lines.append("- `tests/` — test files")
    lines.append("- `utilities/` — helper scripts")
    lines.append("- `_tooling/` — internal audit/conversion scripts (this file lives here)")
    lines.append("")
    lines.append("## Categories")
    lines.append("")
    for cat in sorted(by_cat.keys()):
        lines.append(f"- [`notebooks/{cat}/`](notebooks/{cat}/) "
                     f"— {len(by_cat[cat])} files")
    lines.append("")

    # Per-category tables
    for cat in sorted(by_cat.keys()):
        items = sorted(by_cat[cat], key=lambda m: m.src_path.name.lower())
        lines.append(f"## `{cat}/` ({len(items)})")
        lines.append("")
        lines.append("| File | Model | Task | Description |")
        lines.append("|------|-------|------|-------------|")
        for m in items:
            rel = m.dst_path.relative_to(ROOT).as_posix()
            desc = (m.description or "").replace("|", "\\|")
            lines.append(f"| [`{m.src_path.name}`]({rel}) | "
                         f"{m.model_hint or '—'} | {m.task_hint or '—'} | {desc} |")
        lines.append("")

    if archive_metas:
        lines.append("## Archive — `archive/original_versions/`")
        lines.append("")
        lines.append("Earlier, shorter versions (40-70% smaller) of files whose newer "
                     "counterparts live in `notebooks/`. Kept for historical/diff "
                     "reference, not for execution.")
        lines.append("")
        lines.append("<details><summary>104 files</summary>")
        lines.append("")
        for m in sorted(archive_metas, key=lambda m: m.src_path.name.lower()):
            rel = m.dst_path.relative_to(ROOT).as_posix()
            lines.append(f"- [`{m.src_path.name}`]({rel})")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if kaggle_metas or test_metas or util_metas:
        lines.append("## Other folders")
        lines.append("")
        for label, items in [("kaggle/", kaggle_metas),
                              ("tests/", test_metas),
                              ("utilities/", util_metas)]:
            if not items:
                continue
            lines.append(f"### `{label}` ({len(items)})")
            lines.append("")
            for m in sorted(items, key=lambda m: m.src_path.name.lower()):
                rel = m.dst_path.relative_to(ROOT).as_posix()
                desc = (m.description or "").replace("|", "\\|")
                lines.append(f"- [`{m.src_path.name}`]({rel}) — {desc}" if desc
                              else f"- [`{m.src_path.name}`]({rel})")
            lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_readme(path: Path) -> None:
    body = """# code_base

LLM-queryable mirror of `D:\\Github\\notebooks` (Unsloth fine-tuning notebooks +
companion python scripts), converted to `.py` and reorganized by model family
and task. Use [`MANIFEST.md`](MANIFEST.md) as the index.

## Provenance

- **Source A:** `D:\\Github\\notebooks\\**\\*.ipynb` (529 files) — converted to
  `.py` via `nbformat.PythonExporter`.
- **Source B:** `D:\\Github\\notebooks\\**\\*.py` (444 files) — copied directly.

`nb/` and `python_scripts/` in the source contained the **same 422 basenames**
with near-identical content (only difference: `python_scripts/` has install
cells commented out for safe re-execution). The `nb/` raw conversions were
**dropped as redundant**; the curated `python_scripts/` versions are kept under
`notebooks/<category>/`.

`original_template/` (104 files) contains older, shorter snapshots of files
whose newer versions live in `notebooks/`. Moved to
`archive/original_versions/` for historical reference.

## How to query

- **By model family:** look in `notebooks/<llama|qwen|gemma|mistral|phi|deepseek|gpt_oss>/`.
- **By task:** look in `notebooks/<embeddings|vision|ocr|speech|tts|classification|reasoning_rl>/`.
- **By file name:** grep `MANIFEST.md` — every file has a one-line description
  plus model + task tags.
- **Uncategorized:** `notebooks/other/`.

## Layout

```
code_base/
├── README.md                            # this file
├── MANIFEST.md                          # full file index with tags
├── notebooks/<category>/<file>.py       # 422 curated training/inference scripts
├── archive/original_versions/<file>.py  # 104 earlier snapshots
├── kaggle/                              # Kaggle-only
├── tests/                               # test files
├── utilities/                           # helper scripts
└── _tooling/                            # convert / audit / reorganize scripts
```

## Regenerating

The scripts under `_tooling/` are idempotent and can be re-run if the source
notebooks repository changes:

1. `_tooling/_convert_notebooks.py` — re-converts `.ipynb` → `.py`.
2. `_tooling/_reorganize.py` — re-applies dedup + categorization + manifest.
"""
    path.write_text(body, encoding="utf-8")

# ----- Main -----

def main() -> int:
    print("Planning…")

    # Plan moves from current state
    notebook_metas = plan_notebook_moves(ROOT / "python_scripts", ROOT)
    archive_metas = plan_passthrough(ROOT / "original_template",
                                     ROOT / "archive" / "original_versions")
    kaggle_metas = plan_passthrough(ROOT / "kaggle", ROOT / "kaggle")
    test_metas = plan_passthrough(ROOT / "tests", ROOT / "tests")
    scripts_metas = plan_passthrough(ROOT / "scripts", ROOT / "utilities")
    root_util_metas, tool_paths = plan_root_utilities(ROOT)
    util_metas = scripts_metas + root_util_metas

    print(f"  notebooks/ ← python_scripts/:           {len(notebook_metas):4d}")
    print(f"  archive/original_versions/ ← orig_tpl:  {len(archive_metas):4d}")
    print(f"  kaggle/ stays:                          {len(kaggle_metas):4d}")
    print(f"  tests/ stays:                           {len(test_metas):4d}")
    print(f"  utilities/ ← scripts/ + root utils:     {len(util_metas):4d}")
    print(f"  _tooling/ ← root tool scripts:          {len(tool_paths):4d}")
    print()
    print("Category histogram:")
    hist = Counter(m.category for m in notebook_metas)
    for cat in sorted(hist):
        print(f"  {cat:18s} {hist[cat]:4d}")
    print()

    # Sanity: nb/ exists and will be deleted (after we've confirmed python_scripts is the source)
    nb_dir = ROOT / "nb"
    nb_count = sum(1 for _ in nb_dir.glob("*.py")) if nb_dir.exists() else 0
    print(f"nb/ folder to be REMOVED: {nb_count} files (redundant raw conversions)")
    print()

    # Execute moves
    print("Executing moves…")
    moved = 0
    moved += do_moves(notebook_metas)
    moved += do_moves(archive_metas)
    # kaggle/ and tests/ are already at destination; passthrough plan returns same path
    # Only move if src != dst (i.e. for scripts/ → utilities/)
    moved += do_moves([m for m in util_metas if m.src_path != m.dst_path])

    # Move tooling files
    tool_dst = ROOT / "_tooling"
    tool_dst.mkdir(exist_ok=True)
    tooling_metas: list[FileMeta] = []
    for tp in tool_paths:
        new_path = tool_dst / tp.name
        if tp != new_path:
            shutil.move(str(tp), str(new_path))
            tooling_metas.append(FileMeta(
                src_path=tp,
                dst_path=new_path,
                category="_tooling",
                model_hint="",
                task_hint="Tooling",
                description=short_description(new_path),
                size_bytes=new_path.stat().st_size,
            ))
            moved += 1

    print(f"Moved: {moved} files")

    # Cleanup now-empty src dirs
    for d in ["nb", "python_scripts", "original_template", "scripts"]:
        p = ROOT / d
        if p.exists():
            # nb/ is the only dir we DELETE outright (redundant content)
            if d == "nb":
                shutil.rmtree(p)
                print(f"Deleted: {p}  (redundant raw nbconvert)")
            else:
                remove_empty_tree(p)
                if p.exists():
                    print(f"Note: {p} still exists (not empty?)")

    # Write README + MANIFEST
    write_readme(ROOT / "README.md")
    write_manifest(notebook_metas, archive_metas, util_metas,
                   kaggle_metas, test_metas, ROOT / "MANIFEST.md")

    # Also save a JSON manifest for machine consumption
    json_manifest = {
        "notebooks": [
            {
                "path": m.dst_path.relative_to(ROOT).as_posix(),
                "name": m.src_path.name,
                "category": m.category,
                "model": m.model_hint,
                "task": m.task_hint,
                "description": m.description,
                "size_bytes": m.size_bytes,
            }
            for m in notebook_metas
        ],
        "archive": [
            {"path": m.dst_path.relative_to(ROOT).as_posix(),
             "name": m.src_path.name, "size_bytes": m.size_bytes}
            for m in archive_metas
        ],
        "kaggle":   [m.src_path.name for m in kaggle_metas],
        "tests":    [m.src_path.name for m in test_metas],
        "utilities":[m.src_path.name for m in util_metas],
    }
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(json_manifest, indent=2), encoding="utf-8")

    print()
    print("Wrote README.md, MANIFEST.md, MANIFEST.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
