# CLAUDE.md — Accounting LLM Framework

Lean root context. Pointers and **critical project-wide gotchas only**. The repo's layered context lives in **README files at each level** and **8 lens agent files** under `.claude/agents/` — this file points at them, it doesn't duplicate them.

## Read first, every session

1. [.meta/ROADMAP.md](.meta/ROADMAP.md) — Pat's live verdict per surface + ranked next steps. **Source of truth for what's PASS / HOLD / FAIL right now.**
2. [.meta/hardware.md](.meta/hardware.md) — compatibility matrix; which host row is ★ ACTIVE determines algorithm defaults.
3. The `SessionStart` hook (`.claude/hooks/session_start.py`) auto-runs [.meta/probe_host.py](.meta/probe_host.py) and surfaces the current host + version pins.

## Critical gotchas (project-wide)

- **Idempotent ETL is a hard contract.** `eval/extract_word_tables.py` → `eval/ingest_spiceland.py` → `eval/split_multi_seed.py` must produce byte-identical output on byte-identical inputs. `git diff eval/spiceland9e.jsonl` returning empty after re-run is the test. Non-determinism is a FAIL — fix the source, don't pin the output.
- **Pin everything; no `latest`.** Models, tokenizers, embedding models, LLM-judge prompts all pinned. Datasets carry sha256 (`spiceland9e-v1.1.0` → `fed6eb17de8be1e4…`); runs carry `adapter_sha256` in `manifest.json`.
- **`--no-deps` for unsloth / unsloth_zoo / bitsandbytes on the ACTIVE row (NGC container).** Pip MUST NOT re-resolve PyTorch / CUDA / Triton — they are container-managed. Any recipe that drops `--no-deps` is rejected.
- **Word `~$*.docx` / `~$*.xlsx` are lockfiles.** Diana's ETL excludes them; `.gitignore` excludes them; never read or commit them.
- **Word is authoritative over Excel.** When the Spiceland Excel and Word disagree (LO text missing, MC mislabel, truncated rationale), Word wins. Diana's noise rules encode this.
- **Never retire a host row from the [hardware matrix](.meta/hardware.md).** Rows are `★ ACTIVE`, `dormant`, or `future`. Dormant rows are prescriptive the moment a session runs on that host again.
- **Destruction gate (per [.philosophy/philosophy_statement.md §8](.philosophy/philosophy_statement.md)).** STOP-tier ops (`rm -rf`, force-push to `main`, dropping tables) refuse without explicit consent — and `.claude/settings.json` `permissions.deny` enforces this at the harness layer. CONFIRM-tier ops (destructive `bkill`, prod overwrites) get a one-line "about to do X, OK?" first.

## Architecture — 8 lens agents

Six domain lenses fan out in parallel; **Pat** synthesizes last. Pattern: hierarchical-with-parallel-processing (Anthropic, *Building Effective AI Agents* §Hybrid). Dispatch by name via the Agent tool. Full roster + dataflow at [.claude/agents/README.md](.claude/agents/README.md).

| Lens | Owns | Dispatch when |
|------|------|---------------|
| [Pat](.claude/agents/pat-pm.md) | Synthesis · post-implementation checklist · session-start host check | "what's the verdict?", "is this ready to ship?", "session-start check" |
| [Carla](.claude/agents/carla-cpa.md) | GAAP / IFRS / ASC correctness · JE balance · gold-key adjudication | "is this GAAP-correct?", "does the JE balance?" |
| [Diana](.claude/agents/diana-data.md) | Spiceland ETL · JSONL schema · noise rules · idempotency | "re-run the ETL", "chapter×Bloom distribution?" |
| [Riley](.claude/agents/riley-retrieval.md) | RAG chunking · embeddings · citation discipline | "recall@5 for X?", "retrieval-quality metric" |
| [Solomon](.claude/agents/solomon-solver.md) | Reasoning pattern (CoT vs ReAct) · accounting tools | "why did the solver get this wrong?" |
| [Vera](.claude/agents/vera-verifier.md) | Eval harness · slice tables · mechanical checks · PASS/FAIL | "run the eval", "did this regress?" |
| [Edie](.claude/agents/edie-educator.md) | Tutoring wrapper · hint ladders · grader-coach | "wrap this for tutoring", "grade this student" |
| [Leo](.claude/agents/leo-llm.md) | Model selection · fine-tune recipe · serving stack · quant | "wall-time projection?", "GGUF export plan?" |

For a full fan-out review, dispatch multiple lenses in parallel in a single message; Pat closes. Token budget: one fan-out per project-shaping decision; single-lens dispatch for narrower questions (per [.philosophy/philosophy_statement.md §5](.philosophy/philosophy_statement.md)).

## Layered context — where local conventions live

The blog's "subdirectory CLAUDE.md" principle is satisfied here by **README files + agent files**, which already document each surface in depth. Don't add `CLAUDE.md` files alongside these — that's duplication.

| Surface | Read for local conventions |
|---------|----------------------------|
| `eval/` (Diana's ETL + Vera's harness) | [eval/README.md](eval/README.md) + [.claude/agents/diana-data.md](.claude/agents/diana-data.md) + [.claude/agents/vera-verifier.md](.claude/agents/vera-verifier.md) |
| `models/` (Leo's recipes + runs) | [.meta/hardware.md](.meta/hardware.md) + [.meta/ROADMAP.md §4](.meta/ROADMAP.md) + per-recipe READMEs (e.g. `models/recipes/dgx_spark/README.md`) + [.claude/agents/leo-llm.md](.claude/agents/leo-llm.md) |
| `.meta/` (truth layer — Pat's surface) | The files in `.meta/` document themselves; [.meta/ROADMAP.md](.meta/ROADMAP.md) is the entrypoint. Pat owns edits. |
| `data/` (raw corpora) | `data/Intermediate Financial Accounting test bank/PROVENANCE.md` + `data/GAAP Data/PROVENANCE.md` + [.meta/sources_relationship.md](.meta/sources_relationship.md) |
| `.philosophy/` (the credo) | [.philosophy/philosophy_statement.md](.philosophy/philosophy_statement.md) |

## Versioning (semver-shaped, three tracks)

```
dataset    : spiceland9e-vMAJOR.MINOR.PATCH   →  active: v1.1.0 (sha fed6eb17de8be1e4…)
pipeline   : pipeline-vMAJOR.MINOR.PATCH      →  active: v0.3.0
model run  : <family>-<size>-<prec>-<method>-s<NN>-r<R>   →  in flight: qwen3-4b-4bit-qlora-s00-r0
```

Bumps justified by **what changed**, never by elapsed time. Full policy at [.meta/ROADMAP.md §1](.meta/ROADMAP.md).

## Harness layer (what `.claude/` provides)

- **`.claude/agents/`** — 8 lens definitions; dispatched by name. The repo's "specialized roles" mechanism — richer than skills.
- **`.claude/settings.json`** — deterministic enforcement: destructive Bash deny, build-artifact noise filters, SessionStart hook wiring.
- **`.claude/hooks/session_start.py`** — auto-runs `probe_host.py`, surfaces ROADMAP pointers + version pins + lens-dispatch reminder.
- **`.claude/settings.local.json`** — per-developer overrides (gitignored).

No skills, no MCP servers, no plugins, no HARNESS.md. The agent roster + README layer already covers what those would.
