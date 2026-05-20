"""
Fix categorization: the first reorg used \\b...\\b regex which failed to match
Llama3 / Gemma2 / Qwen3 etc. (digit after letters isn't a word boundary).
This script re-walks notebooks/* and moves misplaced files, then regenerates
MANIFEST.md / MANIFEST.json.

Idempotent — safe to re-run after dataset edits.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(r"D:\Github\accounting\code_base")
NB = ROOT / "notebooks"

# Ordered priority. First match wins. Patterns are simple substrings/regex
# without word-boundary requirements, since filenames embed model versions
# like "Llama3_1_(3B)" which break \b assertions.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("llama",          [r"llama"]),
    ("qwen",           [r"qwen", r"qwq"]),
    ("gemma",          [r"gemma", r"codegemma"]),
    ("mistral",        [r"mistral", r"mixtral", r"magistral"]),
    ("phi",            [r"\bphi[0-9_-]"]),
    ("deepseek",       [r"deepseek"]),
    ("gpt_oss",        [r"gpt[-_ ]?oss"]),
    ("ocr",            [r"ocr", r"nanonets"]),
    ("vision",         [r"vision", r"pixtral", r"idefics", r"janus",
                         r"llava", r"vlm", r"intern[-_]?vl", r"moondream"]),
    ("speech",         [r"whisper", r"\basr\b", r"voxtral"]),
    # TTS: \btts\b fails for "Llasa_TTS_" (underscore is a word char).
    # Use case-sensitive TTS or surround with [_-/.] separators.
    ("tts",            [r"(?:^|[_\-/. ])tts(?:[_\-/. ]|$)", r"orpheus",
                         r"sesame[-_]csm", r"oute[-_]?tts", r"f5[-_]tts",
                         r"kokoro", r"\bcsm\b", r"llasa", r"spark[-_]tts"]),
    ("embeddings",     [r"bge[-_]?m3", r"minilm", r"modernbert", r"embedding",
                         r"nomic"]),
    ("classification", [r"\bbert\b", r"classification"]),
    ("reasoning_rl",   [r"grpo", r"reasoning", r"cot[-_]finetune",
                         r"codeforces", r"reinforcement[-_]learning"]),
    # Other brand-name model families
    ("falcon",         [r"falcon"]),
    ("ernie",          [r"ernie"]),
    ("granite",        [r"granite"]),
    ("smol",           [r"smol"]),
    ("nemotron",       [r"nemotron", r"nemo[-_]gym"]),
    ("liquid_lfm",     [r"\blfm[0-9.]*\b", r"liquid[-_]lfm"]),
    ("glm",            [r"\bglm[-_0-9]"]),
    ("zephyr",         [r"zephyr"]),
    ("function_calling",[r"functiongemma", r"function[-_]calling", r"tool[-_]calling"]),
]

def categorize(name: str) -> str:
    base = name.lower()
    for cat, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, base):
                return cat
    return "other"

MODEL_PATTERNS = [
    (r"(Llama[0-9._-]*[A-Za-z]*)", "Llama"),
    (r"(Qwen[0-9._-]*[A-Za-z]*)", "Qwen"),
    (r"(Gemma[0-9._-]*[A-Za-z]*[Nn]?)", "Gemma"),
    (r"(FunctionGemma)", "FunctionGemma"),
    (r"(CodeGemma)", "CodeGemma"),
    (r"(Mistral[0-9._-]*[A-Za-z]*)", "Mistral"),
    (r"(Mixtral[0-9._-]*[A-Za-z]*)", "Mixtral"),
    (r"(Magistral)", "Magistral"),
    (r"(Phi[0-9._-]*[A-Za-z]*)", "Phi"),
    (r"(Deepseek[0-9._-]*[A-Za-z_]*)", "Deepseek"),
    (r"(GPT[-_]?OSS[0-9._-]*[A-Za-z]*)", "gpt-oss"),
    (r"(Whisper[0-9._-]*[A-Za-z]*)", "Whisper"),
    (r"(Orpheus[0-9._-]*[A-Za-z]*)", "Orpheus"),
    (r"(BGE[-_]?M3)", "BGE-M3"),
    (r"(All_MiniLM_L6_v2)", "all-MiniLM-L6-v2"),
    (r"(ModernBert)", "ModernBERT"),
    (r"(Falcon[-_]?H?[0-9]*)", "Falcon"),
    (r"(Pixtral)", "Pixtral"),
    (r"(Idefics)", "Idefics"),
    (r"(Janus)", "Janus"),
    (r"(LLAVA|LLaVA|Llava|llava)", "Llava"),
    (r"(ERNIE[_0-9A-Za-z]*)", "ERNIE"),
    (r"(Granite[0-9._]*)", "Granite"),
    (r"(Smol[A-Za-z0-9_-]*)", "SmolLM"),
    (r"(BERT|bert)", "BERT"),
]

TASK_PATTERNS = [
    (r"GRPO", "GRPO"),
    (r"DPO", "DPO"),
    (r"ORPO", "ORPO"),
    (r"SFT", "SFT"),
    (r"LoRA", "LoRA"),
    (r"Reinforcement[-_ ]?Learning", "RL"),
    (r"\bRL\b", "RL"),
    (r"OCR", "OCR"),
    (r"Inference", "Inference"),
    (r"Eval(uation)?", "Eval"),
    (r"Vision", "Vision"),
    (r"Audio", "Audio"),
    (r"Conversational", "Conversational"),
    (r"Alpaca", "Alpaca-SFT"),
    (r"Classification", "Classification"),
    (r"Embedding", "Embedding"),
    (r"Reasoning", "Reasoning"),
    (r"Function[-_]?Calling|FunctionGemma|Tool[-_]?Calling", "Function-Calling"),
    (r"Text(_Completion)?", "Text"),
    (r"TTS", "TTS"),
    (r"Synthetic_Data", "Synthetic-Data"),
    (r"cot[-_]Finetune", "CoT-Finetune"),
    (r"CodeForces", "CodeForces"),
    (r"Phone_Deployment|Mobile", "On-device"),
    (r"LMStudio", "LMStudio"),
    (r"Multi-Turn|Multi_Turn", "Multi-Turn"),
]

def extract_first(patterns: list[tuple[str, str]], name: str) -> str:
    for pat, label in patterns:
        if re.search(pat, name, re.IGNORECASE):
            return label
    return ""

_SKIP_HEADERS = re.compile(
    r"^(installation|news|home|index|table of contents|introduction|setup|"
    r"prerequisites|requirements|imports|optional|unsloth|discord|"
    r"unsloth studio|model|inference|training|train|data|load model|"
    r"save (the )?model|save|finetune|saving)$",
    re.IGNORECASE,
)

# Markdown headers from nbconvert appear as either
#   "# ### Heading"            (live cell)
# or
#   "# # ### Heading"          (further-commented install cell)
# Require explicit markdown header markers; do not match shebangs or
# arbitrary comment lines.
# `(#{2,})` requires at least two consecutive `#` so we don't match nbconvert
# cell markers like `# # In[ ]:` (where the second `#` would otherwise satisfy `#+`).
_MD_HEADER_RE = re.compile(r"^#\s*(?:#\s*)?(#{2,})\s+(.+?)\s*$")

def short_description(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    for raw in lines[:200]:
        # Explicit early skips for non-header lines
        if raw.startswith("#!") or raw.startswith("# coding:") or raw.startswith("# -*-"):
            continue
        m = _MD_HEADER_RE.match(raw)
        if not m:
            continue
        head = m.group(2).strip()
        # Drop any residual nested markdown markers (rare)
        head = re.sub(r"^#+\s+", "", head).strip()
        if not head or len(head) < 4:
            continue
        if head.startswith(("<", "[", "*", "!")):
            continue
        if "unsloth.ai" in head.lower() or "discord" in head.lower():
            continue
        if _SKIP_HEADERS.match(head):
            continue
        return head[:110]
    return ""

@dataclass
class FileMeta:
    path: Path
    name: str
    category: str
    model_hint: str
    task_hint: str
    description: str
    size_bytes: int

def main() -> int:
    # Walk every .py under notebooks/ and decide where it should live.
    metas: list[FileMeta] = []
    moves = 0
    for src in sorted(NB.rglob("*.py")):
        if not src.is_file():
            continue
        new_cat = categorize(src.name)
        dst = NB / new_cat / src.name
        if dst != src:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moves += 1
            src = dst  # update for downstream metadata
        metas.append(FileMeta(
            path=src,
            name=src.name,
            category=new_cat,
            model_hint=extract_first(MODEL_PATTERNS, src.name),
            task_hint=extract_first(TASK_PATTERNS, src.name),
            description=short_description(src),
            size_bytes=src.stat().st_size,
        ))
    print(f"Recategorization moves: {moves}")

    # Remove empty subdirs (e.g. old `other/` if everything got reassigned)
    for sub in NB.iterdir():
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()
            print(f"Removed empty: {sub.name}")

    hist = Counter(m.category for m in metas)
    print()
    print("Final category histogram:")
    for cat in sorted(hist):
        print(f"  {cat:18s} {hist[cat]:4d}")

    # Re-collect archive / kaggle / tests / utilities for manifest
    archive_dir = ROOT / "archive" / "original_versions"
    archive_files = sorted(archive_dir.iterdir()) if archive_dir.exists() else []
    kaggle_files = sorted((ROOT / "kaggle").iterdir()) if (ROOT / "kaggle").exists() else []
    tests_files = sorted((ROOT / "tests").iterdir()) if (ROOT / "tests").exists() else []
    util_files = sorted((ROOT / "utilities").iterdir()) if (ROOT / "utilities").exists() else []

    # Write manifests
    write_manifest(metas, archive_files, util_files, kaggle_files, tests_files,
                   ROOT / "MANIFEST.md")
    write_json(metas, archive_files, util_files, kaggle_files, tests_files,
                ROOT / "MANIFEST.json")
    print()
    print("Updated MANIFEST.md and MANIFEST.json")
    return 0

def write_manifest(metas: list[FileMeta], archive_files, util_files,
                   kaggle_files, tests_files, path: Path) -> None:
    by_cat: dict[str, list[FileMeta]] = defaultdict(list)
    for m in metas:
        by_cat[m.category].append(m)

    lines: list[str] = []
    lines.append("# code_base MANIFEST")
    lines.append("")
    lines.append("Index of all files in `code_base/`, grouped by category.")
    lines.append("Source: Unsloth notebooks (`D:\\Github\\notebooks`) converted to `.py`.")
    lines.append("")
    lines.append(f"- Notebook scripts: **{len(metas)}** across **{len(by_cat)}** categories")
    lines.append(f"- Archived earlier versions: **{len(archive_files)}**")
    lines.append(f"- Kaggle: **{len(kaggle_files)}**  |  Tests: **{len(tests_files)}**  "
                  f"|  Utilities: **{len(util_files)}**")
    lines.append("")
    lines.append("## Categories (jump table)")
    lines.append("")
    for cat in sorted(by_cat.keys()):
        lines.append(f"- [`notebooks/{cat}/`](notebooks/{cat}/) — {len(by_cat[cat])} files")
    lines.append("")

    for cat in sorted(by_cat.keys()):
        items = sorted(by_cat[cat], key=lambda m: m.name.lower())
        lines.append(f"## `notebooks/{cat}/` ({len(items)})")
        lines.append("")
        lines.append("| File | Model | Task | Description |")
        lines.append("|------|-------|------|-------------|")
        for m in items:
            rel = m.path.relative_to(ROOT).as_posix()
            desc = (m.description or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| [`{m.name}`]({rel}) | {m.model_hint or '—'} | "
                         f"{m.task_hint or '—'} | {desc} |")
        lines.append("")

    if archive_files:
        lines.append(f"## `archive/original_versions/` ({len(archive_files)})")
        lines.append("")
        lines.append("Earlier, shorter snapshots (40-70% smaller) of files whose newer "
                     "versions live in `notebooks/`. Kept for historical/diff reference.")
        lines.append("")
        lines.append("<details><summary>Show file list</summary>")
        lines.append("")
        for f in archive_files:
            if f.is_file():
                rel = f.relative_to(ROOT).as_posix()
                lines.append(f"- [`{f.name}`]({rel})")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    for label, files, blurb in [
        ("kaggle", kaggle_files, "Kaggle-specific notebooks."),
        ("tests", tests_files, "Test files imported from source."),
        ("utilities", util_files, "Helper / batch-update scripts."),
    ]:
        if not files:
            continue
        lines.append(f"## `{label}/` ({len(files)})")
        lines.append("")
        lines.append(blurb)
        lines.append("")
        for f in files:
            if f.is_file():
                rel = f.relative_to(ROOT).as_posix()
                lines.append(f"- [`{f.name}`]({rel})")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_json(metas, archive_files, util_files, kaggle_files, tests_files,
                path: Path) -> None:
    data = {
        "notebooks": [
            {
                "path": m.path.relative_to(ROOT).as_posix(),
                "name": m.name,
                "category": m.category,
                "model": m.model_hint,
                "task": m.task_hint,
                "description": m.description,
                "size_bytes": m.size_bytes,
            }
            for m in metas
        ],
        "archive": [
            {"path": f.relative_to(ROOT).as_posix(), "name": f.name,
             "size_bytes": f.stat().st_size}
            for f in archive_files if f.is_file()
        ],
        "kaggle":   [f.name for f in kaggle_files if f.is_file()],
        "tests":    [f.name for f in tests_files if f.is_file()],
        "utilities":[f.name for f in util_files if f.is_file()],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())
