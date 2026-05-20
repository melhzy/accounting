---

# My Philosophy for Building With AI Agents

*A working credo to apply at the start of every new project.*

I do not treat AI as a tool to be prompted. I treat it as an **architecture to be designed**. Every new project begins by asking how the system should *think*, *remember*, *act*, and *coordinate*, before I write a single line of model-facing code. This document is the lens through which I commit to approaching that design.

---

**1. I design at the level of modules, not prompts.**
Every agent I build is decomposed into four engineering surfaces: **Planning, Memory, Tool Use, and Action Execution**. Planning turns a goal into tractable subtasks. Memory carries both short-term working state and long-term retrieval over prior knowledge. Tool Use is the bridge to the outside world through APIs, search, code, and databases. Action Execution is what actually changes state. Before I optimize anything, I make sure each of these four surfaces is named, scoped, and independently testable. If I cannot point to where each module lives in my codebase, the project is not yet ready to scale. In multi-agent designs Planning may live at the orchestrator level rather than per-agent — that's a valid architectural choice, but I name the level explicitly so I don't lose track of which one owns task decomposition.

**2. I choose my reasoning pattern deliberately.**
I use **Chain-of-Thought** when the task is closed-world and self-contained, and the model has all the facts it needs in context. I use **ReAct** whenever the task requires external evidence, because its *Thought → Action → Observation* loop is the only reliable defense against hallucination in a knowledge-grounded setting. I never default to one or the other out of habit. I pick the pattern that matches the epistemic shape of the task, and I document that choice so future debugging knows where to look.

**3. I assume multi-agent design until proven unnecessary, and I name the architectural pattern.**
A single agent has a bounded perspective and a single failure mode. I begin every non-trivial project by asking whether the work decomposes into specialized roles, planner, researcher, coder, critic, executor, and whether structured disagreement between them would improve the output — or, in lighter cases, structured independent perspectives reconciled by an explicit arbiter. Debate cycles are higher fidelity but cost more tokens; pick the pattern that matches the decision's reversibility. I define the collaboration protocol explicitly: who speaks when, who has veto power, how shared state is passed. **I name the pattern from a published taxonomy** (Anthropic's *Building Effective AI Agents*: single-agent, hierarchical, collaborative, sequential, parallel, evaluator-optimizer, hybrid). ADAM Lab uses **hierarchical-with-parallel-processing** — Pat as central supervisor, six lens sub-agents fanning out in parallel, synthesis back through Pat. Naming the pattern keeps the architecture honest: it must match a known shape or be justified as a deliberate hybrid. Multi-agent design is not a complication to add later; it is a default to justify removing — and the pattern name is how I know what I'm justifying.

**4. I validate through implementation, not through theory.**
No concept in this philosophy is real to me until it has survived contact with a working system. I commit to starting implementation before I feel ready, because latency budgets, cost ceilings, reproducibility, evaluation pipelines, and edge-case behavior only reveal themselves through deployment. For every project, I define the smallest end-to-end version that exercises all four modules, and I build that first. Polishing comes after the loop closes.

**5. I evaluate before I see results, and I build observable systems.**
Especially in scientific work, an agent that cannot be reproduced is an agent that cannot be trusted. I version my prompts, seed my randomness, log my tool calls, and define evaluation criteria *before* I see results. I borrow the standards from my microbiome and ML pipelines and translate them to agent behavior — end-to-end smoke instead of multi-seed validation, prompt-version tagging instead of seed logging, two-path layout verification instead of leakage-aware splits, token-cost tracking with the same rigor as wall-time. **Observability is a first-class concern, not a debugging afterthought** (per Anthropic's *Building Effective AI Agents* §Build observable systems): when an agent fails, I need visibility into prompt chains, model decision paths, retrieval contexts, and token consumption — not just a stack trace. The four token counts (input / output / cache_read / cache_creation) are non-negotiable to surface. I track tokens-per-fan-out the way I track wall-time and cost in HPC pipelines: a multi-agent review that costs *X* tokens is a budget item, not a free move. A team review that runs every commit is a team review that runs out of money — I budget one full fan-out per project-shaping decision and prefer single-lens dispatch for narrower questions.

**6. I keep the loop continuous.**
Theory without implementation produces frameworks no one uses. Implementation without theory produces systems no one can debug. My discipline is to alternate between them on every project: study, build, observe failure, return to architecture, rebuild. The four modules, the two reasoning patterns, the multi-agent layer, and the implementation feedback are not a one-time checklist. They are a loop I re-enter every time the problem changes.

**7. I make the credo concrete in the agents I ship.**
Every principle above must be visible in the agent definitions, not just in this document. In the ADAM Lab `sci_dashboard` project the credo lives at `.claude/agents/` as seven role-specific lenses (Maya UX, Iris UI, Ben backend, Sasha server-end, Quinn QA, Hank cluster, Pat PM-arbiter — Pat uses the arbitration pattern from §3: independent lenses speak, single synthesizer commits the verdict), each declaring its **reasoning pattern** (CoT vs ReAct vs hybrid), the **memory files it depends on**, the **tools it can use**, and explicit **PASS/FAIL evaluation criteria** for its review. The orchestrator skill `~/.claude/skills/adam_lab/SKILL.md` enforces the collaboration protocol: who speaks when, who has veto power, how shared state flows through Pat's synthesis. If a principle in this document does not have a counterpart in an agent file, the principle has not yet survived contact with a working system — and §4 says it isn't real to me yet.

**8. I gate every irreversible action — and every irreversible UI state.**
Agents that can edit files, run shells, or deploy to production need a safety doctrine, not a hope. I name two tiers: **STOP** — refuse without per-command explicit consent (`rm -rf`, force-push to `main`, secret rotation, dropping production tables, killing other users' jobs); **CONFIRM** — one-line "about to do X, OK?" before destructive `bkill`, prod overwrites, retention sweeps that delete rows. Routine, low-risk operations (read queries, dev-side `bsub`, local edits) need no gate. The discipline is independent of whether I trust the agent — autonomy is not the same as authorization, and an unbounded agent with shell access is not an agent, it is a hazard. Action-gating is the back-end half; the front-end half is **escape-hatch invariants** — overlays, modals, and drawers must never cover the tab strip, the macOS window chrome, or their own close affordance, and global keyboard shortcuts (⌘1, ⌘2, Esc) must always reach the user's intent regardless of which surface holds focus. Action-gating prevents data loss; escape-hatch invariants prevent control loss. The two are dual; both are non-negotiable.

---

**Project initialization checklist (derived from the above):**
Before I commit to building, I can answer all eight questions:

1. Where does each of the four modules live, and at which level — agent or orchestrator?
2. Which reasoning pattern fits this task — chain-of-thought, ReAct, or hybrid?
3. What would a multi-agent decomposition look like, and is debate or arbitration the right reconciliation pattern?
4. What is the smallest end-to-end version I can ship?
5. How will I evaluate, reproduce, and budget the cost of it?
6. Where in the build-observe-rebuild loop am I right now?
7. For every principle above, where in the codebase is its counterpart agent file?
8. For every irreversible action this system can take, which gate — STOP or CONFIRM — protects it?