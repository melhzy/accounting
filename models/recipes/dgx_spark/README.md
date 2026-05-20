# `models/recipes/dgx_spark/` — DGX Spark training recipe

Container-aware recipe for `qwen3-4b-4bit-qlora-s00-r0`. Substrate-of-record is the
[NVIDIA DGX Spark Unsloth playbook](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/unsloth).
Hardware context: `.meta/hardware.md`. Run-id scheme: `.meta/ROADMAP.md` §1.

## Files

| File | Surface | Owner |
|------|---------|-------|
| `launch.sh` | host-side; launches NGC container + JupyterLab | Leo (durable) |
| `qwen3_4b_4bit_qlora_s00_r0.ipynb` | in-container; the recipe | Leo (experimental) |
| `README.md` | operator notes | Leo |

## Run

```bash
# from repo root
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

**Browser**: open `http://127.0.0.1:8888/lab` and navigate to
`models/recipes/dgx_spark/qwen3_4b_4bit_qlora_s00_r0.ipynb`.

**VS Code**:
1. Install the *Jupyter* extension if absent.
2. Open the notebook file in VS Code.
3. `Cmd/Ctrl-Shift-P` → *Jupyter: Specify Jupyter Server for Connections* →
   *Existing* → enter `http://127.0.0.1:8888/?token=` (empty token field).
4. Select the kernel; cells run inside the container.

## Outputs

| Path | What | Gitignored |
|------|------|------------|
| `models/runs/qwen3-4b-4bit-qlora-s00-r0/` | adapter checkpoint, tokenizer, trainer state | yes (large) |
| `models/runs/qwen3-4b-4bit-qlora-s00-r0/manifest.json` | Leo's run manifest (commit this) | no |
| `models/runs/qwen3-4b-4bit-qlora-s00-r0/probe_predictions.jsonl` | 50-sample probe | yes |
| `models/runs/qwen3-4b-4bit-qlora-s00-r0/checkpoint-*/` | intermediate checkpoints | yes |

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
- [ ] `models/runs/qwen3-4b-4bit-qlora-s00-r0/manifest.json` emitted.
- [ ] Update `.meta/ROADMAP.md` §2 row "Training recipe (Leo)" PASS.
