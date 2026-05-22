# Accounting LLM Framework

A domain-grounded reasoning system for **intermediate financial accounting**. Solves, explains, verifies, and grades accounting problems with explicit citations to authoritative sources. Designed as a fan-out of specialised lenses (CPA, data, retrieval, solver, verifier, educator, LLM, PM) coordinated by a single synthesizer — pattern: **hierarchical-with-parallel-processing** ([Anthropic, *Building Effective AI Agents* §Hybrid](.philosophy/philosophy_statement.md#3-i-assume-multi-agent-design-until-proven-unnecessary)).

## Status (2026-05-20)

| Surface | State | Anchor |
|---|---|---|
| Data (canonical corpus) | **PASS** | `spiceland9e-v1.1.0` · sha `fed6eb17de8be1e4…` (4,453 records) |
| Splits (5-seed scenario-grouped) | **PASS** | per-seed sha pinned in [eval/sft/splits/manifest.json](eval/sft/splits/manifest.json) |
| Pipeline (ETL) | **PASS** | `pipeline-v0.3.0`, three-stage idempotent |
| Hardware substrate | **PASS-refreshed** | DGX Spark / GB10 Blackwell (sm_120) / aarch64 Ubuntu 24.04 / 119.6 GB UMA |
| Training recipe | **r0 in flight** | `qwen3-4b-4bit-qlora-s00-r0` — see [models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/](models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/) |
| Eval harness | **HOLD** | `eval/run.py + diff_runs.py + mechanical_checks.py` pending Vera authoring |
| Retrieval (RAG) | **deferred** | GAAP corpus ready; chunking + index post-r0 |
| Solver loop | **deferred** | substrate validated; loop wires up after eval harness |
| Agent roster | **PASS** | 8 lenses ([.claude/agents/](.claude/agents/)) |

Read [.meta/ROADMAP.md](.meta/ROADMAP.md) for the live verdict per surface and the prioritized next steps. Read [.meta/devlog.md](.meta/devlog.md) for chronological work history.

## What this builds on

Two corpora, one doctrine.

| Corpus | Source | Vintage | Role | Provenance |
|---|---|---|---|---|
| **Test bank** | Spiceland *Intermediate Accounting* 9e | ©2018 (drafted mid-2017) | Eval target — Vera scores against the gold answers | [data/.../PROVENANCE.md](data/Intermediate%20Financial%20Accounting%20test%20bank/PROVENANCE.md) |
| **GAAP** | FASB Accounting Standards Codification | Late-Jan 2026 export (ASUs through 2025-12) | Authoritative reference — solver + tutor cite this | [data/GAAP Data/PROVENANCE.md](data/GAAP%20Data/PROVENANCE.md) |

The corpora are **~8 years apart in vintage**. The doctrine for how that gap is handled (which standard governs scoring vs. teaching, where to flag drift, what the model's `gaap_supersession` block looks like, the top-5 drift topics) lives at [.meta/sources_relationship.md](.meta/sources_relationship.md). Diana's v1.1.0 emission stamps every record with a `meta` block that pre-computes the drift catalog (CECL receivables, convertibles + EPS, goodwill, tax intraperiod, crypto) so Vera can join by id at eval time.

## Architecture — 8 lenses

Six domain lenses fan out in parallel on every non-trivial review. **Pat** synthesizes the verdict last. **Leo** owns the model substrate that the other lenses run on.

| Lens | Owns | Model |
|---|---|---|
| [Pat](.claude/agents/pat-pm.md) | Synthesis · verdicts · post-implementation checklist · session-start host check | opus-4-7 |
| [Carla](.claude/agents/carla-cpa.md) | CPA / GAAP / IFRS / ASC correctness; gold-key adjudication | opus-4-7 |
| [Diana](.claude/agents/diana-data.md) | Spiceland ETL · JSONL schema · noise rules · idempotency | opus-4-7 |
| [Riley](.claude/agents/riley-retrieval.md) | Chunking · embeddings · citation discipline · retrieval-quality metrics | opus-4-7 |
| [Solomon](.claude/agents/solomon-solver.md) | Reasoning patterns (CoT / ReAct) · accounting tool set · prompt | opus-4-7 |
| [Vera](.claude/agents/vera-verifier.md) | Regression harness · slice tables · mechanical post-hoc checks | sonnet-4-6 |
| [Edie](.claude/agents/edie-educator.md) | Tutoring wrapper · hint ladders · grader-coach · error-pattern catalog | sonnet-4-6 |
| [Leo](.claude/agents/leo-llm.md) | Model selection · fine-tune recipe · serving stack · quantization · cost/latency | opus-4-7 |

See [.claude/agents/README.md](.claude/agents/README.md) for the roster-level dataflow and the per-lens reasoning pattern. See [.philosophy/philosophy_statement.md](.philosophy/philosophy_statement.md) for the credo each lens implements.

## Hardware target

**NVIDIA DGX Spark** (GB10 Grace-Blackwell SoC). Substrate-of-record is the [NVIDIA DGX Spark Unsloth playbook](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth).

```
arch       : aarch64 (arm64)
OS         : Linux Ubuntu 24.04
GPU        : NVIDIA GB10 · sm_120 · compute_cap 12.1 · driver 580.95.05
memory     : 119.6 GB unified LPDDR5X (UMA — CPU and GPU share the pool)
container  : nvcr.io/nvidia/pytorch:25.11-py3   (CUDA 13.0 · PyTorch 2.10.0a0+nv25.11)
unsloth    : 2026.5.5 (auto-enables DGX Spark optimisations)
serving    : vLLM (in-container) for batch eval · llama.cpp / Ollama for portable GGUF
```

Full machine profile + recipe + troubleshooting at [.meta/hardware.md](.meta/hardware.md). UMA OOM-recovery is a buffer-cache flush, **not** OOM-kill:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

If you ever move the repo to a different machine, run [.meta/probe_host.py](.meta/probe_host.py) before anything else — Pat's session-start check compares the probe output against `.meta/hardware.md` and flags drift in OS family, CPU arch, GPU model, or critical ML packages. Stale algorithm defaults from a prior host can silently degrade training; the host check is the guard.

## Versioning

Three independent semver-shaped tracks. See [.meta/ROADMAP.md §1](.meta/ROADMAP.md) for the full policy.

```
dataset    : spiceland9e-vMAJOR.MINOR.PATCH   →  active: v1.1.0 (sha fed6eb17de8be1e4…)
pipeline   : pipeline-vMAJOR.MINOR.PATCH      →  active: v0.3.0
model run  : <family>-<size>-<prec>-<method>-s<NN>-r<R>   →  in flight: qwen3-4b-4bit-qlora-s00-r0
```

## Repository layout

```
.
├── .meta/                                   project-wide truth (every session reads this first)
│   ├── ROADMAP.md                           Pat's live verdict per surface + prioritized next steps
│   ├── devlog.md                            append-only chronological work log
│   ├── hardware.md                          machine profile + substrate-of-record + algorithm constraints
│   ├── sources_relationship.md              test-bank ↔ GAAP doctrine (scoring, solver, tutor, retrieval)
│   ├── v1_1_0_plan.md                       v1.1.0 corpus implementation plan
│   ├── host.json                            machine-readable output of probe_host.py
│   └── probe_host.py                        session-start host probe
│
├── .claude/agents/                          8 lens definition files + roster README
├── .philosophy/                             the credo this project implements
│
├── data/                                    raw source corpora (versioned in git for reproducibility)
│   ├── Intermediate Financial Accounting test bank/
│   │   ├── excel/       21 chapter workbooks (canonical ETL input)
│   │   ├── word/        21 chapter answer keys (rationale fallback)
│   │   └── PROVENANCE.md
│   └── GAAP Data/                           FASB ASC PDFs + paired .txt, by topic cluster
│       └── PROVENANCE.md
│
├── eval/                                    Diana's pipeline + Vera's harness (planned)
│   ├── extract_word_tables.py               .docx → spiceland9e_tables.jsonl
│   ├── ingest_spiceland.py                  Excel + tables.jsonl → canonical spiceland9e.jsonl
│   ├── _format.py                           shared SFT chat-template renderer
│   ├── split_multi_seed.py                  5-seed scenario-grouped Bloom-stratified 80/10/10
│   ├── spiceland9e.jsonl                    canonical corpus (4,453 records · v1.1.0)
│   ├── spiceland9e_tables.jsonl             1,687 extracted Word tables
│   ├── sft/splits/seed_{00..04}__*/         per-seed train/valid/test + manifests
│   ├── stats/run_v1.1.0.json                row reconciliation + per-chapter/Bloom counts
│   ├── diana_warnings.log                   ETL warnings (v1.1.0 changelog at top)
│   └── README.md                            Diana's pipeline docs
│
├── models/
│   ├── recipes/dgx_spark/                   Leo's r0 recipe (notebook + launch.sh + README)
│   └── runs/<run_id>/                       per-run adapter + manifest + probe predictions
│
├── .code_base/                              experimental notebook playground (per model family)
│   └── notebooks/                           qwen/, llama/, phi/, gemma/, deepseek/, ...
│
└── unsloth_compiled_cache/                  ephemeral Unsloth runtime patcher cache (gitignored)
```

## Quick start

Session-start (always — Pat reads `.meta/host.json` to detect machine drift):

```bash
python .meta/probe_host.py    # → regenerates .meta/host.json
```

Open the recipe for r0 interactively (launches NGC container + JupyterLab on `127.0.0.1:8888`):

```bash
bash models/recipes/dgx_spark/launch.sh
# then open models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb
```

ETL re-run on the host (conda base; pure-Python deps):

```bash
pip install openpyxl python-docx seedhash
python eval/extract_word_tables.py     # .docx → spiceland9e_tables.jsonl   (idempotent)
python eval/ingest_spiceland.py        # → spiceland9e.jsonl                 (idempotent)
python eval/split_multi_seed.py        # → eval/sft/splits/seed_{00..04}__*/ (idempotent)
```

After re-emission, Diana's contract guarantees byte-identical output on byte-identical inputs — `git diff eval/spiceland9e.jsonl` returning empty is the idempotency check.

## Where to start reading

- **New to the project**: [.philosophy/philosophy_statement.md](.philosophy/philosophy_statement.md) (the credo) → this README → [.claude/agents/README.md](.claude/agents/README.md) (the team)
- **About to ship a change**: [.meta/ROADMAP.md](.meta/ROADMAP.md) (current verdicts + next steps) → relevant lens file in [.claude/agents/](.claude/agents/) → [.meta/sources_relationship.md](.meta/sources_relationship.md) if your change touches scoring or solver content
- **Debugging a substrate issue**: [.meta/hardware.md](.meta/hardware.md) (substrate-of-record) → [models/recipes/dgx_spark/README.md](models/recipes/dgx_spark/README.md) (operator notes)
- **Working with the data corpus**: [eval/README.md](eval/README.md) (Diana's pipeline) → [.meta/sources_relationship.md](.meta/sources_relationship.md) (authority order) → [data/.../PROVENANCE.md](data/Intermediate%20Financial%20Accounting%20test%20bank/PROVENANCE.md) (test-bank vintage) + [data/GAAP Data/PROVENANCE.md](data/GAAP%20Data/PROVENANCE.md) (GAAP vintage)

## Working with the team

When working on this repo with Claude Code, dispatch the relevant lens by name. Examples:

- "Carla, is this revenue-recognition treatment ASC 606-correct?"
- "Diana, re-run the ETL and surface the per-chapter row delta."
- "Riley, audit recall@5 for Chapter 15 leases."
- "Solomon, why did the bond amortization come out wrong?"
- "Leo, what's the wall-time projection for Qwen3-14B-bf16-LoRA on this substrate?"
- "Vera, run the regression slice and give me PASS/FAIL."
- "Edie, wrap this answer for tutoring mode."
- "Pat, synthesize."

For a fan-out review, dispatch multiple lenses in parallel in a single message; Pat closes.

## Hard constraints (every lens enforces these)

- **Correctness over fluency.** A confident, fluent answer without GAAP grounding is a regression.
- **Grounded over confident.** Retrieval-grounded answers cite `(Chapter, LO, Topic)` from Spiceland and `(ASC Topic-Subtopic-Section-Paragraph)` from GAAP when relevant.
- **Eval-before-feel.** Vera's PASS/FAIL on regression slices outranks any subjective "feels better" claim.
- **Pin everything.** No `latest` aliases on models, tokenizers, embedding models, or LLM-judge prompts. Every adapter carries `adapter_sha256`, every dataset carries its sha anchor.
- **Idempotent ETL.** Re-running on byte-identical inputs produces byte-identical JSONL. Non-determinism is a FAIL.
- **Destruction gate.** STOP / CONFIRM tiers per [.philosophy/philosophy_statement.md §8](.philosophy/philosophy_statement.md). Each lens's agent file lists the irreversible operations under its surface.

---

_Pat-synthesised, 2026-05-20. Refreshed on every session-start host check (Pat) and every ratified ROADMAP edit (Pat)._
