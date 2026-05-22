# `models/recipes/dgx_spark/` — DGX Spark training recipes

Container-aware recipes targeting the DGX Spark row. Substrate-of-record is the
[NVIDIA DGX Spark Unsloth playbook](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth).
Hardware context: `.meta/hardware.md`. Run-id scheme: `.meta/ROADMAP.md` §1.

## 5-10B thinking-model candidate ledger

The user's ask: *suitable LLMs for the accounting framework, 5B-10B, thinking models*.
The dgx_spark row's UMA ceiling permits anything in this range comfortably at
4-bit QLoRA. Picks below are filtered against the
[Unsloth model catalog](https://unsloth.ai/docs/get-started/unsloth-model-catalog),
text-only (vision-thinking variants excluded — Spiceland is text + JSONL),
filed by lineage.

| Model | Size | Thinking surface | Decision |
|---|---|---|---|
| `unsloth/Qwen3-8B`                       | 8B dense | hybrid (toggle via chat template)              | **r1 — built** (size ablation vs r0) |
| `unsloth/DeepSeek-R1-0528-Qwen3-8B`      | 8B dense | R1 RL distill on Qwen3 backbone                | **r2 — built** (reasoning prior on r1) |
| `unsloth/DeepSeek-R1-Distill-Llama-3-8B` | 8B dense | R1 distill on Llama 3 backbone                 | deferred — different family/tokenizer breaks the controlled chain; revisit if r2 ≈ r1 and the user wants to test cross-family reasoning priors |
| `unsloth/DeepSeek-R1-Distill-Qwen-2.5-7B`| 7B dense | R1 distill on Qwen 2.5 backbone                | deferred — older Qwen lineage; r2 already covers the Qwen-family R1-distill case with a newer base |
| `unsloth/Ministral-3-8B-Reasoning`       | 8B dense | native Mistral reasoning variant               | deferred — different tokenizer (Mistral SP); useful as a family-diversity probe but would need a separate ablation chain |
| `unsloth/Qwen3-VL-8B-Thinking`           | 8B dense | thinking + vision                              | **excluded** — multimodal; we'd pay for an image encoder we never use |
| `unsloth/Phi-4-Mini-Reasoning`           | ~3.8B    | native Phi-4 reasoning variant                 | **excluded** — below the 5B floor |
| `unsloth/Phi-4-Reasoning`                | ~14B     | native Phi-4 reasoning variant                 | **excluded** — above the 10B ceiling |
| `unsloth/Gemma-4-E4B`                    | "effective 4B" MatFormer | hybrid                | **excluded** — below the 5B floor at active-params |

**Why two stubs and not five**: the value of r0 → r1 → r2 is that each hop
varies exactly one thing (param count, then pretraining lineage). Adding
Mistral/Llama-family models in the same chain would compound the
tokenizer/family variable with whatever else changes, and we'd lose the
clean single-variable reading. Family-diversity probes belong in a
*separate* chain rooted at its own r0-equivalent baseline, not bolted onto
this one. Build them when the user has a question only family-diversity
answers — e.g. if r2 ≈ r1, the question "is Qwen-family the right family?"
becomes worth the extra chain.

## Recipe chain

| Run | Base | Tests | Variable isolated | Status |
|-----|------|-------|-------------------|--------|
| r0  | `unsloth/Qwen3-4B-Instruct-2507`         | baseline                 | — | **executed**, 69.2% |
| r1  | `unsloth/Qwen3-8B`                       | r1 vs r0 → size delta    | parameter count (4B→8B) | prepared |
| r2  | `unsloth/DeepSeek-R1-0528-Qwen3-8B`      | r2 vs r1 → prior delta   | pretraining lineage (vanilla→R1-distill) | prepared |

- **`qwen3_4b_4bit_qlora_s00_r0.ipynb`** — executed; metrics at
  `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/test_metrics.json`.
- **`qwen3_8b_4bit_qlora_s00_r1.ipynb`** — prepared, not executed. Generated
  from r0 by `_build_r1_notebook.py`.
- **`dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb`** — prepared, not executed.
  Generated from r1 by `_build_r2_notebook.py` (chain: r0 → r1 → r2). Same
  parameter count and backbone shape as r1; only the pretraining lineage
  differs.

All three share corpus anchor (`spiceland9e-v1.1.0`), seed (`seed_00 / 351199285`),
hyperparameters, LoRA rank/alpha, and target modules. Two adjacent runs in the
table differ on exactly one variable — that is the value of the chain.

## Files

| File | Surface | Owner |
|------|---------|-------|
| `launch.sh` | host-side; launches NGC container + JupyterLab | Leo (durable) |
| `qwen3_4b_4bit_qlora_s00_r0.ipynb` | in-container; r0 recipe (executed) | Leo (experimental) |
| `qwen3_8b_4bit_qlora_s00_r1.ipynb` | in-container; r1 recipe (prepared) | Leo (experimental) |
| `dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb` | in-container; r2 recipe (prepared) | Leo (experimental) |
| `_build_r1_notebook.py` | host-side; emits r1.ipynb by diff-patching r0 | Leo (durable) |
| `_build_r2_notebook.py` | host-side; emits r2.ipynb by diff-patching r1 | Leo (durable) |
| `README.md` | operator notes | Leo |

## Run

```bash
# from repo root — launches the container, then open r0, r1, or r2 inside JupyterLab
bash models/recipes/dgx_spark/launch.sh
```

`launch.sh` will:

1. Verify the NGC image `nvcr.io/nvidia/pytorch:25.11-py3` is present locally
   (pulled by the 2026-05-20 smoke test); pull if absent.
2. Kill any stale container named `accounting-dgx-spark`.
3. Launch with `--gpus all --ulimit memlock=-1 --ulimit stack=67108864 --ipc=host`
   (playbook prescription + `--ipc=host` for PyTorch DataLoader SHM).
4. Bind-mount the repo at `/workspace` and the host HF cache at
   `/workspace/.hf_cache` so model weights survive container restarts.
5. Inside the container: `pip install` (deps) then `pip install --no-deps unsloth
   unsloth_zoo bitsandbytes` (load-bearing — see `.meta/hardware.md` §ML stack).
6. Start JupyterLab on `127.0.0.1:8888` with no token, no LAN exposure.

Override the port with `JUPYTER_PORT=9999 bash models/recipes/dgx_spark/launch.sh`.

## Connect

**Browser**: open `http://127.0.0.1:8888/lab` and navigate to one of:

- `models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb` — executed baseline
- `models/recipes/dgx_spark/qwen3_8b_4bit_qlora_s00_r1.ipynb` — prepared, size ablation
- `models/recipes/dgx_spark/dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb` — prepared, reasoning-prior ablation

**VS Code**:
1. Install the *Jupyter* extension if absent.
2. Open the notebook file in VS Code.
3. `Cmd/Ctrl-Shift-P` → *Jupyter: Specify Jupyter Server for Connections* →
   *Existing* → enter `http://127.0.0.1:8888/?token=` (empty token field).
4. Select the kernel; cells run inside the container.

## Outputs

| Path | What | Gitignored |
|------|------|------------|
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/` | adapter checkpoint, tokenizer, trainer state | yes (large) |
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/manifest.json` | Leo's run manifest (commit this) | no |
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/probe_predictions.jsonl` | 50-sample probe | yes |
| `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/checkpoint-*/` | intermediate checkpoints | yes |

## Smoke-test reference (2026-05-20)

| Knob | Confirmed |
|------|-----------|
| Image | `nvcr.io/nvidia/pytorch:25.11-py3` |
| PyTorch | `2.10.0a0+nv25.11` |
| CUDA | runtime 13.0, toolkit 13.0 (container) |
| Unsloth | 2026.5.5 (auto-enables DGX Spark optimizations) |
| bitsandbytes | 0.49.2 |
| trl | 0.26.1 |
| datasets | 4.3.0 |
| Triton | 3.5.0 (sm_120-compatible) |
| Throughput | **4.30 samples/s, 0.538 steps/s** (Phi-3.5-mini, r=16, batch=2, grad-accum=4) |
| Features lit | bfloat16, FA2, padding-free auto, double-buffer, gradient offload |

**r0 wall-clock projection**: 3,538 train rows × 3 epochs / 4.3 ≈ **41 min**.
Five-seed sweep ≈ **3.5 h**.

## UMA OOM-recovery

If training stalls on memory pressure on the 119.6 GB unified pool, the
playbook-prescribed first response is to flush the host page cache:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

This is **not** an OOM-kill — DGX Spark's UMA means CPU and GPU share the same
LPDDR5X bytes. Page-cache pressure from one side starves the other. The flush
gives the GPU back its share without changing the recipe. Do **not** reduce
`max_seq_length` or batch size as a first response.

## Post-r2 trajectory (sketched, not built)

Two natural next moves once r1 and r2 have executed and Vera has produced
slice tables for both:

- **r3 = synthetic thinking traces on the r2 base.** Use a teacher model
  (full DeepSeek-R1, or GPT-4-class) to synthesize `<think>...</think>`
  blocks for each Spiceland record, then SFT the whole
  `<think>...</think>` + answer sequence with `enable_thinking=True`. This
  is the only way to actually *train* the thinking behavior on accounting
  content — r1 and r2 train only the answer half, leaving thinking as
  pre-existing inference-time capability. r3 is expensive (teacher
  inference cost, teacher pin discipline) and pollutes the
  single-variable chain, so it belongs in its own branch off r2 rather
  than as a direct successor.
- **Eval-side follow-up for r1/r2.** The current
  `_build_eval_notebook.py` / `_build_judge_notebook.py` /
  `_build_two_stage_judge.py` hardcode `qwen3-4b-4bit-qlora-s00-r0` as
  `RUN_ID`. Once r1 (and then r2) executes and emits its `manifest.json`
  + adapter, the eval builders should be parameterized on RUN_ID so the
  same eval surface lights up across the chain. Premature to refactor
  now; the manifests don't exist yet, and shapes may need adjusting once
  we see the first r1 outputs.

## Open issues (Leo, 2026-05-20)

These do **not** block r0. They are tracked here so the user and Pat can see
them before r1.

### A. Supersession-note rendering — DEFERRED to r1

Pat's `.meta/v1_1_0_plan.md` §1 calls for `eval/_format.py` to template-render
`meta.gaap_supersession` into the assistant turn. **Verified absent**:
`render_assistant_message` in `eval/_format.py` only consumes `gold_answer` and
`explanation`. Diana's split JSONL also drops the `gaap_supersession` block from
the slim per-record `meta`, so even inline-rendering in the notebook §2 has no
upstream data to consume on the current split files (sha
`5dce67f97fe300c1…` for seed_00 train).

**r0 call**: train on raw Spiceland gold. Drift is a post-hoc Vera eval column,
not a training-time loss signal. r1 needs either (a) Diana plumbs the
supersession block into split-record `meta`, or (b) `_format.py` renders it
into the assistant turn before split-time, then Diana re-emits splits with a
new sha.

### B. Loss weighting 0.85/0.15 — DEFERRED to r1

Pat's `.meta/v1_1_0_plan.md` "Loss-weighting note" calls for 0.85 gold /
0.15 supersession. `SFTTrainer` does not support per-segment loss weighting
out of the box. r0 trains uniformly (1.0/1.0); the 6.6 %–296/4452 drift slice
naturally under-weights itself in the data mix. r1 revisit with a custom
collator emitting per-token loss weights — gated by (A) being resolved first.

### C. Vera eval scaffolding — out of Leo's scope

`eval/run.py + diff_runs.py + mechanical_checks.py` are Vera's track. The
`§9` probe in the notebook is a 50-sample sanity-check, **not** the production
eval. Do not interpret the probe predictions as a Vera verdict.

## r0 launch gate

User-triggered. The recipe is *prepared*, not *executed*. Trigger phrasing:
"Leo, launch r0 from `models/recipes/dgx_spark/`."

Pre-launch checklist (Leo runs):

- [ ] `bash models/recipes/dgx_spark/launch.sh` → JupyterLab reachable.
- [ ] Open the notebook; §1 cell PASSES (device check, sha check).
- [ ] `cat /sys/fs/cgroup/memory.peak` baseline before §7.
- [ ] Run §2–§10 (or §2–§9; GGUF flag off by default).
- [ ] `models/runs/dgx_spark/qwen3-4b-4bit-qlora-s00-r0/manifest.json` emitted.
- [ ] Update `.meta/ROADMAP.md` §2 row "Training recipe (Leo)" PASS.

## r1 launch gate — Qwen3-8B size ablation

User-triggered. Recipe is *prepared*, not *executed*. **Requires the DGX Spark
row to be ACTIVE again** (see `.meta/ROADMAP.md` §0; today's ACTIVE row is
Windows, so r1 is queued behind that host pointer move). Trigger phrasing:
"Leo, launch r1 from `models/recipes/dgx_spark/`."

Why r1 = Qwen3-8B (not Qwen3-4B-Instruct-2507 like r0):

- Controlled size ablation: same family/tokenizer, only base-model size changes.
  Lets the user attribute any accuracy delta to capacity, not to tokenizer or
  pretraining mix.
- Qwen3-8B is hybrid (instruct + thinking). The recipe sets
  `enable_thinking=False` in the chat template so the thinking prior is
  preserved — gold has no `<think>` traces; training with thinking ON would
  damage the capability.

Wall-time projection: r0 trained at 1.933 samples/s on this host (91.5 min for
3,537 rows × 3 epochs). 8B at the same hyperparameters projects to
**~180–200 min** (3.0–3.3 h). UMA absorbs the extra activation memory; no batch
reduction needed.

Pre-launch checklist (Leo runs):

- [ ] `bash models/recipes/dgx_spark/launch.sh` → JupyterLab reachable.
- [ ] Open `qwen3_8b_4bit_qlora_s00_r1.ipynb`; §1 cell PASSES.
- [ ] Confirm the sample render in §2 has **no** `<think></think>` block (proves
      `enable_thinking=False` took effect on the Qwen3-8B chat template).
- [ ] Run §2–§10 (GGUF flag is OFF by default in r1; flip after Vera PASS).
- [ ] `models/runs/dgx_spark/qwen3-8b-4bit-qlora-s00-r1/manifest.json` emitted.
- [ ] Run `eval/diff_runs.py` against the r0 manifest for the cross-size delta.

After r1 closes, the natural next step is **r2** — already prepared as
`dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb` below.

## r2 launch gate — DeepSeek-R1-0528-Qwen3-8B reasoning-prior ablation

User-triggered. Recipe is *prepared*, not *executed*. **Requires the DGX Spark
row to be ACTIVE again** and **r1 should be launched first** so the chain
r0 → r1 → r2 produces two single-variable deltas instead of a
two-variable jump. Trigger phrasing: "Leo, launch r2 from `models/recipes/dgx_spark/`."

Why r2 = DeepSeek-R1-0528-Qwen3-8B (not Qwen3-8B like r1):

- Same Qwen3 backbone shape and tokenizer as r1 → LoRA rank 16 sees the same
  projection dimensions → only the pretraining lineage differs. The size
  question is settled by r0→r1; the reasoning-prior question is settled by
  r1→r2.
- DeepSeek-R1-0528-Qwen3-8B has been RL-distilled from DeepSeek-R1 to emit
  `<think>...</think>` reasoning blocks. r2 still trains with
  `enable_thinking=False` (inherited from r1) so the SFT does not damage the
  reasoning prior. **The open question r2 answers**: does that prior survive
  non-thinking-mode SFT and remain useful at inference time?

Wall-time projection: inherits r1's ~180–200 min. Same parameter count, same
backbone, same hyperparameters.

Pre-launch checklist (Leo runs):

- [ ] r1 already executed (so the r1 vs r2 delta is meaningful).
- [ ] `bash models/recipes/dgx_spark/launch.sh` → JupyterLab reachable.
- [ ] Open `dsr1_qwen3_8b_4bit_qlora_s00_r2.ipynb`; §1 cell PASSES.
- [ ] Confirm the sample render in §2 has **no** `<think></think>` block.
- [ ] Run §2–§10 (GGUF flag OFF by default).
- [ ] `models/runs/dgx_spark/dsr1-qwen3-8b-4bit-qlora-s00-r2/manifest.json` emitted.
- [ ] Run `eval/diff_runs.py` against the r1 manifest for the reasoning-prior delta.
- [ ] Run a separate Vera eval with thinking ENABLED at inference time
      (the prior only pays off if it survives — that is the column to measure).
