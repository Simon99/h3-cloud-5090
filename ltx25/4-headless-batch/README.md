# Pkg 4 | Headless cloud batch (officials ship drag-in UI files only — no automation)

[中文版 →](README.zh.md)

The full unattended chain: **boot → upgrade ComfyUI → download models (per-file size gate) → version gate → run batch → per-shot download + ffprobe verify → wind down the lease**.

| File | Role |
|---|---|
| `precmd.sh` | Container boot pre-step: upgrade to 0.34.3 via codeload tarball (dodges datacenter git rate-limits) + parallel model downloads, each size-verified (catches LFS pointers / error pages saved as `.safetensors`) |
| `ltx25_run.py` | Direct-API runner: builds the graph (t2v/flf2v shared), submits, polls; **non-empty `node_errors` in the submit response = hard fail** (guards against ComfyUI's "partial output validation failure → silently ignored → HTTP 200" fake-success); exit 2 when ComfyUI is unreachable |
| `run_batch.sh` | Batch engine: per shot "run → download immediately → ffprobe verify", never waits for the whole batch; background lease-renewal heartbeat; exit 2 aborts the batch; on exit the lease drops to a 10-min short fuse (protects against forgetting to shut down) |
| `jobs.example.txt` | Job list: one line per job, `<output_name> <args...>`; use `+` for spaces in prompt-type args |

Usage:
```bash
python3 runpod.py create --precmd="$(cat precmd.sh)"     # see runpod.py at repo root
RUNNER=ltx25_run.py bash run_batch.sh <podId> <outdir> jobs.example.txt
```
All three gates were paid for in real money: the version gate (0.31 had the nodes but the TE
couldn't run), the size gate (git-lfs pointer files blew up twice), and the node_errors gate
(the 20-second fake success).
