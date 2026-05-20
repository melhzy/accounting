# code_base

LLM-queryable mirror of `D:\Github\notebooks` (Unsloth fine-tuning notebooks +
companion python scripts), converted to `.py` and reorganized by model family
and task. Use [`MANIFEST.md`](MANIFEST.md) as the index, or [`MANIFEST.json`](MANIFEST.json)
for programmatic lookup.

## Numbers

| | Source | Result |
|---|---|---|
| `.ipynb` notebooks (converted to `.py`) | 529 | 422 (canonical) |
| `.py` companion scripts (copied) | 444 | 104 archived as earlier versions |
| Helper / test / kaggle / utilities | — | 30 |
| **Total `.py` in `code_base/`** | 973 | **556** |
| **Redundant copies removed**  | | **417** |

## Provenance & dedup logic

- **Source A:** `D:\Github\notebooks\**\*.ipynb` — converted to `.py` via
  `nbformat.PythonExporter` ([`_tooling/_convert_notebooks.py`](_tooling/_convert_notebooks.py)).
- **Source B:** `D:\Github\notebooks\**\*.py` — copied directly.

`nb/` and `python_scripts/` in the source contained the **same 422 basenames**
with near-identical content. The only meaningful diff: `python_scripts/` had
install cells double-commented (`# # ### Installation` → install code prefixed
with `# `) for safe re-execution. The `nb/` raw conversions were **dropped as
redundant**; the curated `python_scripts/` versions are kept under
`notebooks/<category>/`.

`original_template/` (104 files) contained older, shorter snapshots of files
whose newer versions live in `notebooks/`. Moved to `archive/original_versions/`
for historical/diff reference, not for execution.

## How to query

- **By model family:** see the relevant subfolder in `notebooks/` — e.g.
  `notebooks/llama/`, `notebooks/qwen/`, `notebooks/gemma/`.
- **By task:** topic-grouped folders are `embeddings/`, `vision/`, `ocr/`,
  `speech/`, `tts/`, `classification/`, `reasoning_rl/`, `function_calling/`.
- **By file name + tags:** [`MANIFEST.md`](MANIFEST.md) has a table per
  category with `Model`, `Task`, and an extracted description for every file.
- **Programmatic:** [`MANIFEST.json`](MANIFEST.json) ships the same data as a
  flat array suitable for embeddings indexing.

## Categories (`notebooks/<cat>/`)

| Category | Files | Examples |
|---|---|---|
| `llama` | 55 | Llama 3.1/3.2/4, Advanced GRPO, vision variants |
| `qwen` | 94 | Qwen2.5/3, QwQ, Qwen-VL, Qwen-Embedding |
| `gemma` | 80 | Gemma 2/3/3N/4, CodeGemma, EmbeddingGemma, FunctionGemma |
| `mistral` | 25 | Mistral, Mixtral, Magistral |
| `phi` | 13 | Phi-3, Phi-3.5, Phi-4 |
| `deepseek` | 12 | DeepSeek-OCR, R1 distills |
| `gpt_oss` | 41 | gpt-oss (20B / 120B), RL variants |
| `falcon` | 5  | Falcon H1 |
| `ernie` | 3  | ERNIE 4.5 |
| `granite` | 6  | IBM Granite |
| `nemotron` | 10 | NVIDIA Nemotron, NeMo-Gym |
| `liquid_lfm` | 11 | Liquid LFM2 |
| `glm` | 2  | GLM Flash |
| `zephyr` | 3  | Zephyr DPO |
| `embeddings` | 9  | BGE-M3, MiniLM, ModernBERT |
| `vision` | 11 | Pixtral, Idefics, LLaVA, VLMs |
| `ocr` | 3  | Nanonets OCR (+ DeepSeek OCR in `deepseek/`) |
| `speech` | 3  | Whisper, Voxtral |
| `tts` | 18 | Orpheus, Sesame CSM, Llasa, Spark TTS |
| `classification` | 3  | BERT classification |
| `reasoning_rl` | 10 | GRPO / CoT finetune (model-agnostic) |
| `other` | 5  | Synthetic_Data_Hackathon, Unsloth_Studio |

Each file's name carries provenance prefixes that survive the move:
- `AMD-*` — ROCm-specific variant
- `Kaggle-*` — Kaggle-runtime variant
- (no prefix) — Colab/T4 default

## Layout

```
code_base/
├── README.md                            # this file
├── MANIFEST.md                          # human-readable index w/ per-file tags
├── MANIFEST.json                        # machine-readable equivalent
├── notebooks/<category>/<file>.py       # 422 curated training/inference scripts
├── archive/original_versions/<file>.py  # 104 earlier snapshots (reference only)
├── kaggle/                              #   2 Kaggle-specific
├── tests/                               #  13 test files
├── utilities/                           #  10 helper / batch scripts
└── _tooling/                            #   5 audit / convert / reorganize scripts
```

## Regenerating

The scripts under [`_tooling/`](_tooling/) are idempotent and can be re-run if
the source notebooks repo changes:

1. [`_tooling/_convert_notebooks.py`](_tooling/_convert_notebooks.py)
   — re-converts `.ipynb` → `.py` (mirrors source layout into `code_base/`
     before reorg; safe to re-run, no overwrites of moved files).
2. [`_tooling/_recategorize.py`](_tooling/_recategorize.py)
   — re-walks `notebooks/`, fixes any miscategorized file, and rewrites
   `MANIFEST.md` + `MANIFEST.json`. **This is the script to run after editing
   categorization rules.**
3. [`_tooling/_audit_diff.py`](_tooling/_audit_diff.py) /
   [`_tooling/_audit_template.py`](_tooling/_audit_template.py)
   — one-shot audits used during the initial dedup (kept for posterity).
4. [`_tooling/_reorganize.py`](_tooling/_reorganize.py)
   — original full reorg pass (only useful from the pre-reorg source state).
