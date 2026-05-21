"""Builder for the gpt-oss:20b Essay/Problem judge notebook.

Generates `eval_qwen3_4b_qlora_s00_r0_essay_judge.ipynb` next to this file.
Re-runnable. Cross-platform: discovers REPO at runtime, no hardcoded paths.
Auto-probes Ollama at 127.0.0.1 (host) and 172.17.0.1 (container bridge).
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().with_name("eval_qwen3_4b_qlora_s00_r0_essay_judge.ipynb")


def md(text: str) -> dict:
    lines = text.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(text: str) -> dict:
    lines = text.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": src,
    }


CELLS: list[dict] = []
C = CELLS.append

# ============================================================================
# Header
# ============================================================================
C(md("""# `qwen3-4b-4bit-qlora-s00-r0` — Essay/Problem judge (gpt-oss:20b via Ollama)

Scores the 117 `judge_pending` Essay/Problem records left over from the rerun
eval. The deterministic MC/TF/Matching scoring lives in
`eval_qwen3_4b_qlora_s00_r0.ipynb`; this notebook handles the long-form items
that need an LLM judge with a rubric.

**Judge:** `gpt-oss:20b` (Ollama, MXFP4, ~13 GB)
**Inputs:** `eval_rerun/test_predictions.jsonl` (predictions from the rerun)
**Outputs:**
- Updates each Essay/Problem record in `test_predictions.jsonl` with
  `judge_correct`, `judge_rubric_score`, `judge_rationale`, and flips
  `judge_pending` → `False`, `correct` → `judge_correct`.
- Rewrites `test_metrics.json` with Essay/Problem now scored.
- Saves a separate audit log at `eval_rerun/judge_log.jsonl` (one row per call
  with raw prompt + raw response + timing) so a human can sanity-check the
  judge's calls.

**Resumable.** Records that already have a `judge_correct` field are skipped on
re-run. Interrupt safely (Ctrl-C / kernel-restart) — each judgment is flushed
to disk before moving on.

**Cross-platform / cross-context.** Auto-probes Ollama at the host loopback
(`127.0.0.1:11434`) and the Docker bridge gateway (`172.17.0.1:11434`).
Override with the `OLLAMA_BASE_URL` env var if neither works."""))

# ============================================================================
# §1 — Setup
# ============================================================================
C(md("""## §1 — Setup + Ollama reachability probe"""))

C(code("""import os, sys, json, time, platform
from pathlib import Path
import urllib.request
import urllib.error

def _find_repo() -> Path:
    workspace = Path("/workspace")
    if workspace.is_dir() and (workspace / "eval" / "sft" / "splits").is_dir():
        return workspace
    forced = os.environ.get("REPO_ROOT")
    if forced:
        return Path(forced).resolve()
    p = Path.cwd().resolve()
    for d in [p, *p.parents]:
        if (d / ".git").is_dir() or (d / "eval" / "sft" / "splits").is_dir():
            return d
    raise RuntimeError(f"could not find repo root from {p}")

REPO = _find_repo()
print(f"REPO   : {REPO}")
print(f"os     : {platform.system()} {platform.release()}")
print(f"python : {platform.python_version()}")"""))

C(code("""def _probe_ollama(url: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

# Try env override first, then host loopback, then Docker bridge gateway.
CANDIDATE_URLS = []
if os.environ.get("OLLAMA_BASE_URL"):
    CANDIDATE_URLS.append(os.environ["OLLAMA_BASE_URL"].rstrip("/"))
CANDIDATE_URLS += ["http://127.0.0.1:11434", "http://172.17.0.1:11434"]

OLLAMA_URL = None
for url in CANDIDATE_URLS:
    print(f"probing {url} ...", end=" ")
    if _probe_ollama(url):
        OLLAMA_URL = url
        print("OK")
        break
    print("unreachable")

assert OLLAMA_URL, (
    "no Ollama instance reachable. Start it with `ollama serve` on the host, "
    "or set OLLAMA_BASE_URL to a custom address."
)
print(f"\\nusing Ollama at {OLLAMA_URL}")"""))

C(code("""# Confirm the judge model is present
JUDGE_MODEL = "gpt-oss:20b"

req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
with urllib.request.urlopen(req, timeout=5) as r:
    tags = json.loads(r.read())
available = {m["name"] for m in tags.get("models", [])}
print(f"available models ({len(available)}):", sorted(available)[:10],
      "..." if len(available) > 10 else "")
assert JUDGE_MODEL in available, (
    f"{JUDGE_MODEL!r} not in Ollama. Pull it first: `ollama pull {JUDGE_MODEL}`"
)
print(f"\\njudge model {JUDGE_MODEL!r} is available ✓")"""))

# ============================================================================
# §2 — Configuration
# ============================================================================
C(md("""## §2 — Configuration"""))

C(code("""RUN_ID    = "qwen3-4b-4bit-qlora-s00-r0"
RUN_DIR   = REPO / "models" / "runs" / RUN_ID
EVAL_DIR  = RUN_DIR / "eval_rerun"
PRED_PATH = EVAL_DIR / "test_predictions.jsonl"
METRICS_PATH = EVAL_DIR / "test_metrics.json"
JUDGE_LOG = EVAL_DIR / "judge_log.jsonl"

# Judge generation knobs
JUDGE_TEMPERATURE = 0.0     # deterministic verdicts
JUDGE_NUM_PREDICT = 512     # rubric verdict is short; cap to bound latency
JUDGE_FORMAT      = "json"  # Ollama enforces JSON-shaped output

# How many records to judge in this run. None = all judge_pending records.
LIMIT = None

# When True, re-judge records that already have a verdict (useful after rubric tweaks).
FORCE_REJUDGE = False

assert PRED_PATH.is_file(), f"missing predictions: {PRED_PATH}"
print(f"PRED_PATH    : {PRED_PATH}")
print(f"METRICS_PATH : {METRICS_PATH}")
print(f"JUDGE_LOG    : {JUDGE_LOG}")"""))

# ============================================================================
# §3 — Rubric + judge call
# ============================================================================
C(md("""## §3 — Rubric prompt + Ollama call

The judge sees three things per question: the prompt (system + user turns), the
gold rationale from Spiceland 9e, and the model's generation. It returns
strict JSON: a binary `correct`, a 0–3 rubric score, and a one-sentence
rationale. The format flag forces JSON; the rubric prose anchors the verdict.

Why a 4-level rubric on top of binary correctness?
- `correct=True / score=3` and `correct=True / score=2` both pass the eval gate,
  but the score-2 cohort is where the model produces right answers via flaky
  reasoning — that's the cohort to inspect when designing r1.
- `correct=False / score=0` vs `score=1` distinguishes "completely wrong" from
  "right idea, wrong number" — different failure modes need different fixes
  (RAG vs tool-use vs more training data)."""))

C(code("""SYSTEM_PROMPT = (
    "You are an expert accounting examiner grading a student's answer to an "
    "intermediate financial accounting problem from Spiceland's 9th edition. "
    "You apply US GAAP (FASB ASC) strictly. You do not solve the problem "
    "yourself; you compare the student's answer to the gold-standard answer "
    "from the official solution manual and decide whether the student is "
    "correct. Respond with strict JSON only — no prose outside the JSON object."
)

RUBRIC_INSTRUCTIONS = '''Grade the student's answer.

Rubric for the JSON output:
- "correct": true if the student's final answer (numerical value, journal entry,
  or substantive conclusion) matches the gold-standard answer. Allow for legitimate
  alternative phrasings, formatting differences, rounding equivalences, and
  alternative-but-equivalent journal entries. Mark false if the final number is
  wrong, a required journal entry is missing, or the answer violates GAAP.
- "rubric_score": integer 0-3
    0 = wrong final answer, or no answer
    1 = right final answer arrived at via wrong reasoning or with major omissions
    2 = right final answer with mostly-correct reasoning and minor gaps
    3 = right final answer with complete, correctly-cited reasoning
- "rationale": one short sentence explaining the score (cite a specific
  discrepancy or confirm the match).

Output JSON only, no surrounding prose. Example:
{"correct": true, "rubric_score": 2, "rationale": "Final figure $48,000 matches gold; depreciation method named correctly but salvage-value treatment is hand-waved."}
'''

def build_judge_prompt(record: dict, prediction: dict) -> str:
    \"\"\"Construct the judge user-turn content for one record + prediction.\"\"\"
    msgs = record["messages"]
    system_turn = msgs[0]["content"]
    user_turn   = msgs[1]["content"]
    gold        = msgs[2]["content"]
    student     = prediction["generation"]
    qid         = record["meta"]["id"]
    qtype       = record["meta"]["type"]
    return (
        f"=== Question ID: {qid}  ({qtype}) ===\\n\\n"
        f"--- System context shown to the student ---\\n{system_turn}\\n\\n"
        f"--- Question ---\\n{user_turn}\\n\\n"
        f"--- Gold-standard answer (Spiceland 9e solution manual) ---\\n{gold}\\n\\n"
        f"--- Student's answer ---\\n{student}\\n\\n"
        f"{RUBRIC_INSTRUCTIONS}"
    )"""))

C(code("""def call_judge(prompt_user: str, *, timeout: float = 120.0) -> tuple[dict, dict]:
    \"\"\"Send the prompt to Ollama, parse the JSON verdict.

    Returns (verdict_dict, raw_response_dict). The raw_response_dict carries
    timing + tokens for the audit log.
    \"\"\"
    body = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt_user},
        ],
        "format": JUDGE_FORMAT,
        "stream": False,
        "options": {
            "temperature": JUDGE_TEMPERATURE,
            "num_predict": JUDGE_NUM_PREDICT,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read())
    elapsed_ms = (time.time() - t0) * 1000.0

    content = raw.get("message", {}).get("content", "").strip()
    try:
        verdict = json.loads(content)
    except json.JSONDecodeError:
        # Defensive: judge ignored format=json. Salvage by extracting the first {...}.
        import re
        m = re.search(r"\\{.*\\}", content, flags=re.DOTALL)
        verdict = json.loads(m.group(0)) if m else {}

    # Coerce + validate shape
    verdict = {
        "correct"      : bool(verdict.get("correct", False)),
        "rubric_score" : int(verdict.get("rubric_score", 0)) if str(verdict.get("rubric_score", "")).isdigit() else 0,
        "rationale"    : str(verdict.get("rationale", "")).strip(),
    }
    raw_meta = {
        "model"        : raw.get("model", JUDGE_MODEL),
        "total_duration": raw.get("total_duration"),
        "eval_count"   : raw.get("eval_count"),
        "prompt_eval_count": raw.get("prompt_eval_count"),
        "latency_ms"   : round(elapsed_ms, 1),
        "raw_content"  : content,
    }
    return verdict, raw_meta"""))

# ============================================================================
# §4 — Judge loop
# ============================================================================
C(md("""## §4 — Run the judge over `judge_pending` records

Reads `test_predictions.jsonl`, processes each Essay/Problem record that
either has no verdict yet OR `FORCE_REJUDGE=True`, and flushes after each
record. Safe to interrupt and re-run."""))

C(code("""# Load predictions
predictions = []
with PRED_PATH.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            predictions.append(json.loads(line))
print(f"loaded {len(predictions)} predictions")

# Build a quick lookup of test records by id, so we can pull the gold + question
TEST_JSONL = REPO / "eval" / "sft" / "splits" / "seed_00__351199285" / "test.jsonl"
test_by_id = {}
with TEST_JSONL.open(encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        test_by_id[r["meta"]["id"]] = r

# Decide which records to judge
def _needs_judge(p):
    if p["type"] != "Essay/Problem":
        return False
    if FORCE_REJUDGE:
        return True
    return "judge_correct" not in p

todo_idx = [i for i, p in enumerate(predictions) if _needs_judge(p)]
already  = [i for i, p in enumerate(predictions) if p["type"] == "Essay/Problem" and "judge_correct" in p and not FORCE_REJUDGE]
print(f"to judge      : {len(todo_idx)} essay/problem records")
print(f"already judged: {len(already)}  (skip; set FORCE_REJUDGE=True to override)")
if LIMIT is not None:
    todo_idx = todo_idx[:LIMIT]
    print(f"LIMIT applied : will judge {len(todo_idx)} this run")"""))

C(code("""from tqdm.auto import tqdm

EVAL_DIR.mkdir(parents=True, exist_ok=True)

def _flush_predictions():
    with PRED_PATH.open("w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(p, ensure_ascii=False) + "\\n")

def _append_judge_log(entry: dict):
    with JUDGE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\\n")

t_start = time.time()
errors = 0

for i in tqdm(todo_idx, desc="judging"):
    p = predictions[i]
    rec = test_by_id[p["question_id"]]
    user_prompt = build_judge_prompt(rec, p)
    try:
        verdict, raw_meta = call_judge(user_prompt)
    except Exception as exc:  # noqa: BLE001
        errors += 1
        _append_judge_log({
            "question_id": p["question_id"],
            "error": f"{type(exc).__name__}: {exc!s:.500}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        continue

    # Update prediction in-place
    p["judge_correct"]      = verdict["correct"]
    p["judge_rubric_score"] = verdict["rubric_score"]
    p["judge_rationale"]    = verdict["rationale"]
    p["judge_model"]        = JUDGE_MODEL
    p["judge_latency_ms"]   = raw_meta["latency_ms"]
    # Flip status fields so downstream aggregators see this as scored
    p["judge_pending"] = False
    p["scorable"]     = True
    p["correct"]      = bool(verdict["correct"])

    _append_judge_log({
        "question_id": p["question_id"],
        "verdict"    : verdict,
        "raw_meta"   : raw_meta,
        "ts"         : time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    _flush_predictions()  # incremental save

elapsed = time.time() - t_start
print(f"\\ndone: {len(todo_idx) - errors}/{len(todo_idx)} judged in {elapsed:.1f}s")
if errors:
    print(f"  errors: {errors} (see {JUDGE_LOG})")"""))

# ============================================================================
# §4.5 — Re-score deterministic types from existing generations
# ============================================================================
C(md("""## §4.5 — Re-score MC / TF / Matching from existing generations

The deterministic extractors used at generation time may have been wrong
(notably: Matching answers are letters A–O in this dataset, NOT digits — an
early version of the eval notebook looked for digits and gave 0/73 on
Matching). This cell re-applies the **corrected** extractors to the generations
already on disk, so re-running the judge notebook self-heals regardless of
whether the eval notebook was patched. The model is NOT re-invoked — only the
regex-based scoring is recomputed.

Idempotent: if the predictions are already scored correctly, this is a no-op
(same gold/pred/correct values get written back)."""))

C(code("""import re

def extract_predicted(qtype: str, generation: str):
    g = (generation or "").strip()
    if not g:
        return None
    if qtype == "Multiple Choice":
        m = re.search(r"\\*\\*([A-E])\\*\\*", g)
        if m: return m.group(1)
        m = re.search(r"\\b([A-E])\\b", g)
        return m.group(1) if m else None
    if qtype == "True/False":
        if re.search(r"\\b(TRUE|True|true)\\b", g):  return "TRUE"
        if re.search(r"\\b(FALSE|False|false)\\b", g): return "FALSE"
        return None
    if qtype == "Matching":
        m = re.search(r"\\b([A-Z])\\b", g)
        if m: return m.group(1)
        m = re.search(r"\\b(\\d{1,2})\\b", g)
        return m.group(1) if m else None
    return g

def gold_for(rec: dict):
    asst = rec["messages"][2]["content"].strip()
    qtype = rec["meta"]["type"]
    if qtype == "Multiple Choice":
        m = re.match(r"^\\*\\*([A-E])\\*\\*", asst)
        return m.group(1) if m else asst[:1]
    if qtype == "True/False":
        m = re.match(r"^\\*\\*(TRUE|FALSE)\\*\\*", asst, re.IGNORECASE)
        return m.group(1).upper() if m else asst.upper().split()[0]
    if qtype == "Matching":
        m = re.match(r"^([A-Z])\\b", asst)
        return m.group(1) if m else asst[:1]
    return asst

SCORABLE_TYPES = {"Multiple Choice", "True/False", "Matching"}

rescore_changes = 0
for p in predictions:
    if p["type"] not in SCORABLE_TYPES:
        continue
    rec = test_by_id[p["question_id"]]
    new_gold = gold_for(rec)
    new_pred = extract_predicted(p["type"], p["generation"])
    new_correct = bool(new_gold and new_pred and new_gold.strip().upper() == new_pred.strip().upper())
    if (p.get("gold") != new_gold or p.get("pred") != new_pred or p.get("correct") != new_correct):
        rescore_changes += 1
    p["gold"]    = new_gold
    p["pred"]    = new_pred
    p["correct"] = new_correct
    p["scorable"] = True
    p["judge_pending"] = False

# Flush only if anything changed
if rescore_changes:
    with PRED_PATH.open("w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(p, ensure_ascii=False) + "\\n")
    print(f"re-scored {rescore_changes} records (MC/TF/Matching) with corrected extractors; flushed to {PRED_PATH}")
else:
    print("deterministic re-score: no changes (predictions already match corrected extractors)")"""))

# ============================================================================
# §5 — Re-aggregate metrics with judge results
# ============================================================================
C(md("""## §5 — Re-aggregate `test_metrics.json` with Essay/Problem now scored"""))

C(code("""from collections import defaultdict

def _acc_block():
    return {"correct": 0, "scorable": 0, "judge_pending": 0}

by_type    = defaultdict(_acc_block)
by_bloom   = defaultdict(_acc_block)
by_chapter = defaultdict(_acc_block)
overall    = _acc_block()

for p in predictions:
    for b in (by_type[p["type"]], by_bloom[p["primary_bloom"]], by_chapter[p["chapter"]], overall):
        if p["judge_pending"]:
            b["judge_pending"] += 1
        else:
            b["scorable"] += 1
            if p["correct"]:
                b["correct"] += 1

def _with_acc(b):
    return {**b, "accuracy": (b["correct"] / b["scorable"]) if b["scorable"] else None}

# Preserve the original metrics file's run_id/model_dir/test_split/generation_config
prev = json.loads(METRICS_PATH.read_text(encoding="utf-8")) if METRICS_PATH.exists() else {}
metrics = {
    **prev,
    "generated_at"      : time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "n_questions"       : len(predictions),
    "n_scorable"        : overall["scorable"],
    "n_judge_pending"   : overall["judge_pending"],
    "overall_accuracy_scorable": round(overall["correct"] / overall["scorable"], 4) if overall["scorable"] else None,
    "by_question_type"  : {k: _with_acc(v) for k, v in by_type.items()},
    "by_primary_bloom"  : {k: _with_acc(v) for k, v in sorted(by_bloom.items())},
    "by_chapter"        : {str(k): _with_acc(v) for k, v in sorted(by_chapter.items())},
    "judge"             : {
        "model"    : JUDGE_MODEL,
        "ollama_url": OLLAMA_URL,
        "rubric"   : "binary correctness + 0-3 rubric score (see judge prompt in builder)",
        "judged_records": sum(1 for p in predictions if "judge_correct" in p),
    },
}
METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(f"wrote {METRICS_PATH}")
print()
print(f"=== overall: {metrics['overall_accuracy_scorable']:.2%}  ({overall['correct']}/{overall['scorable']} scorable, {overall['judge_pending']} judge-pending) ===")
print()
for t, v in metrics["by_question_type"].items():
    acc = f"{v['accuracy']:.2%}" if v['accuracy'] is not None else "  —  "
    print(f"  {t:<18s}: {acc}  ({v['correct']}/{v['scorable']} scorable, {v['judge_pending']} pending)")"""))

# ============================================================================
# §6 — Visualize
# ============================================================================
C(md("""## §6 — Visualize"""))

C(code("""import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["figure.dpi"] = 110
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False"""))

C(md("""### 6.1 — Accuracy by question type (now with Essay/Problem scored)"""))

C(code("""types = list(metrics["by_question_type"].keys())
type_acc = [metrics["by_question_type"][t]["accuracy"] or 0.0 for t in types]
type_n   = [metrics["by_question_type"][t]["scorable"]      for t in types]
type_jp  = [metrics["by_question_type"][t]["judge_pending"] for t in types]

fig, ax = plt.subplots(figsize=(9, 4.5))
bars = ax.bar(types, type_acc, color=["#4C72B0", "#8172B2", "#C44E52", "#55A868"])
for b, n, jp, acc in zip(bars, type_n, type_jp, type_acc):
    label = f"{acc:.1%}\\nn={n}" + (f" (+{jp} pending)" if jp else "")
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01, label, ha="center", va="bottom", fontsize=9)
ax.set_ylim(0, 1.10)
ax.set_ylabel("Accuracy")
ax.set_title(f"{RUN_ID} — accuracy by question type (Essay/Problem via {JUDGE_MODEL} judge)")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
plt.show()"""))

C(md("""### 6.2 — Rubric-score distribution for Essay/Problem

Shows the spread of judgment scores. A healthy distribution shouldn't be all
0s and 3s — that's a sign the judge is collapsing to binary. Some 1s and 2s
mean the rubric is doing work."""))

C(code("""essay = [p for p in predictions if p["type"] == "Essay/Problem" and "judge_rubric_score" in p]
if essay:
    from collections import Counter
    score_counts = Counter(p["judge_rubric_score"] for p in essay)
    scores = [0, 1, 2, 3]
    counts = [score_counts.get(s, 0) for s in scores]
    colors = ["#C44E52", "#DD8452", "#CCB974", "#55A868"]
    labels = ["0\\nwrong", "1\\nright ans,\\nwrong reason", "2\\nright ans,\\nminor gaps", "3\\nright ans,\\ngood reason"]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(labels, counts, color=colors)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.5, str(c), ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Count")
    ax.set_title(f"Essay/Problem rubric-score distribution (n={len(essay)})")
    plt.tight_layout()
    plt.show()

    n_correct = sum(1 for p in essay if p["judge_correct"])
    print(f"essay correct (judge): {n_correct}/{len(essay)} = {n_correct/len(essay):.2%}")
else:
    print("no judged Essay/Problem records yet — run §4 first.")"""))

C(md("""### 6.3 — Sample inspection (first 5 wrong, first 5 right)

A human should spot-check the judge before trusting the headline number.
Reads natural; gold and student visible side by side."""))

C(code("""wrong = [p for p in essay if not p.get("judge_correct", False)][:5]
right = [p for p in essay if p.get("judge_correct", False)][:5]

def _show(p, tag):
    rec = test_by_id[p["question_id"]]
    print(f"=== {tag}  {p['question_id']}  (rubric_score={p.get('judge_rubric_score','?')}) ===")
    print(f"  judge rationale: {p.get('judge_rationale','')}")
    print(f"  --- gold (first 400 ch) ---")
    print("  " + rec["messages"][2]["content"][:400].replace("\\n", "\\n  "))
    print(f"  --- student (first 400 ch) ---")
    print("  " + (p["generation"][:400] or "").replace("\\n", "\\n  "))
    print()

for p in wrong: _show(p, "WRONG")
for p in right: _show(p, "RIGHT")"""))

# ============================================================================
# Footer
# ============================================================================
C(md("""## Artifacts produced

| Path | What |
|---|---|
| `eval_rerun/test_predictions.jsonl` | updated in-place with `judge_correct`, `judge_rubric_score`, `judge_rationale`, `judge_model`, `judge_latency_ms` on the 117 Essay/Problem records |
| `eval_rerun/test_metrics.json` | overall + slice tables now include Essay/Problem accuracy |
| `eval_rerun/judge_log.jsonl` | one row per judge call: question_id, verdict, raw response, timing — for human audit |

## When the judge gets it wrong

A 20B general-purpose judge will misgrade some accounting items, especially
Apply+ Bloom levels where the gold relies on a specific GAAP nuance. To
escalate from the gpt-oss:20b judge, the playbook paths are:

1. **Bump to `gpt-oss:120b`** — already pulled (65 GB), runs slower but is a stronger reader of long worked solutions. Change `JUDGE_MODEL` in §2 and re-run with `FORCE_REJUDGE=True`.
2. **Two-judge agreement** — call both 20b and 120b; only count as `correct` when they agree. Disagreements go to a human-review queue.
3. **Adjudication by `carla-cpa`** — agent-level CPA review on the disagreement set, since the judge's failure mode is exactly the kind of edge case CPA review is for.

None of those are wired up here; this notebook is the entry point."""))


nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(CELLS)} cells)")
