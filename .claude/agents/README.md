# Accounting LLM Framework — Agent Roster

Seven lenses, one synthesizer. Pattern: **hierarchical-with-parallel-processing** (Anthropic, *Building Effective AI Agents* §Hybrid). Six domain lenses fan out in parallel on every non-trivial review; **Pat** synthesizes the verdict last.

Pin: `claude-opus-4-7` for lenses that exercise judgment over content (Pat, Carla, Diana, Riley, Solomon). `claude-sonnet-4-6` for execution-shaped lenses where speed beats depth (Vera, Edie).

| Lens | Role | Model | Tools | Reasoning |
|------|------|-------|-------|-----------|
| [Pat](pat-pm.md) | PM-arbiter — final verdict + named tradeoff + checklist | opus-4-7 | Read, Grep, Glob | CoT (synthesis) |
| [Carla](carla-cpa.md) | CPA / domain correctness (GAAP, IFRS, ASC) | opus-4-7 | Read, Grep, Glob | Hybrid |
| [Diana](diana-data.md) | Data engineer — Spiceland ETL, JSONL corpus, noise rules | opus-4-7 | Read, Edit, Write, Bash, Grep, Glob | ReAct + CoT |
| [Riley](riley-retrieval.md) | Retrieval / RAG — chunking, embeddings, citation discipline | opus-4-7 | Read, Edit, Write, Bash, Grep, Glob | Hybrid |
| [Solomon](solomon-solver.md) | Solver — reasoning patterns + deterministic accounting tools | opus-4-7 | Read, Edit, Write, Bash, Grep, Glob | CoT for Remember/Understand · ReAct for Apply+ |
| [Vera](vera-verifier.md) | Verifier — eval harness, slice tables, mechanical checks | sonnet-4-6 | Read, Bash, Grep, Glob | ReAct |
| [Edie](edie-educator.md) | Educator — tutoring wrapper, hint ladders, grader-coach | sonnet-4-6 | Read, Edit, Write, Grep, Glob | CoT |

## Dataflow

```
       data/Intermediate Financial Accounting test bank/
         excel/  ←  source of truth (Spiceland 9e, 21 chapters, 4,471 q)
         word/   ←  fallback for truncated rationales
                  │
                  ▼
       Diana ──►  eval/spiceland9e.jsonl  (canonical row-shaped corpus)
                  │
            ┌─────┴─────┐
            ▼           ▼
       Riley         Vera
       rag/index/    eval/runs/run_*/
            │           ▲
            ▼           │
       Solomon ────────►│
       solver/         scores Solomon's outputs against
            │          Diana's gold, slices by Bloom × Difficulty
            ▼          × Chapter × Question_Type
       Edie
       tutor/          ◄── consumes Solomon's raw answer, wraps for learners
            │
            └──► Carla audits content · Pat synthesizes ship/hold
```

## Workflow

1. **Build phase** — Diana ingests Excel → JSONL. Riley indexes JSONL → FAISS. Solomon wires tools + prompts + the Riley retriever.
2. **Eval phase** — Vera runs Solomon against Diana's JSONL, slices results, surfaces regressions. Carla audits content failures.
3. **Tutoring phase** — Edie wraps Solomon's output for learners; grader-coach mode compares student work to gold.
4. **Ship phase** — Pat reads all six lenses' findings, applies the post-implementation checklist (plus LLM extras and data extras where applicable), produces one verdict.

## Invoking the team

When working on this repo with Claude Code, dispatch via the relevant lens by name. Examples:

- "Carla, is this revenue-recognition treatment ASC 606-correct?"
- "Diana, re-run the ETL and surface the per-chapter row delta."
- "Riley, audit recall@5 for Chapter 15 leases."
- "Solomon, why did the bond amortization come out wrong?"
- "Vera, run the regression slice and give me PASS/FAIL."
- "Edie, wrap this answer for tutoring mode."
- "Pat, synthesize."

For a fan-out review, dispatch multiple lenses in parallel in a single message; Pat closes.

## Philosophy

The architecture in this directory implements the credo at [`.philosophy/philosophy_statement.md`](../../.philosophy/philosophy_statement.md). The eight numbered principles map to concrete agent files:

| Philosophy | Implementation |
|------------|----------------|
| §1 Four modules (Planning, Memory, Tool Use, Action Execution) | Pat owns Planning at orchestrator level · all lenses declare auto-memory · Solomon owns Tool Use · Diana/Riley/Solomon/Vera/Edie own Action Execution; Pat/Carla are read-only |
| §2 CoT vs ReAct chosen deliberately | Every lens names its reasoning pattern in its "Reasoning pattern" section |
| §3 Multi-agent by default, name the pattern | hierarchical-with-parallel-processing, named at the top of this README and in every lens |
| §4 Validate through implementation | Vera's eval harness is the validation surface; "tested = run, not compiled" is her hard constraint |
| §5 Observe before results; four token counts | Solomon emits all four (`input`, `output`, `cache_read`, `cache_creation`); Vera checks |
| §6 Continuous loop | Vera's regression-vs-baseline cadence makes this concrete |
| §7 Credo concrete in agents | This file + the seven lens files |
| §8 Gate every irreversible action | Each lens has a "Destruction gate" section with STOP / CONFIRM tiers |

## Current state

This roster ships **before** the implementation it specifies. The next concrete deliverables — in order — are Diana's ETL (Excel → JSONL with noise rules applied), Riley's index over the JSONL, and Vera's first baseline run against a placeholder solver. The roster is the contract those implementations build against.
