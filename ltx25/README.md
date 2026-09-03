# LTX-2.5 — drag-and-run ComfyUI workflows

[中文版 →](README.zh.md)

Three official workflow files in `workflows/` — drag into the ComfyUI window to load (sampling params, sigmas and wiring are all inside the file, no manual setup):

| File | Purpose | Measured on RTX 5090 |
|---|---|---|
| `video_ltx2_5_t2v.json` | Text-to-video (with audio) | 121 frames in 83s, 1920×1088 |
| `video_ltx2_5_flf2v.json` | First/last keyframe lock | 121 frames in ~100s |
| `video_ltx2_5_i2v.json` | Image-to-video | (same class) |

## Configuration notes

1. **ComfyUI must be ≥ 0.34** (older builds have the LTX nodes but the gemma4 text encoder fails at runtime).
2. All model files live on HF [`Lightricks/LTX-2.5`](https://huggingface.co/Lightricks/LTX-2.5); place per folder:

| File | Location | Size |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` ← **pick this on 5090/Blackwell** (template default is int8-convrot, 21.5GB, slower) | `models/diffusion_models/` | 18.7GB |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `models/text_encoders/` | 15.4GB |
| `ltx-2.5-video-vae-bf16.safetensors` | `models/vae/` | 1.5GB |
| `ltx-2.5-audio-vae-bf16.safetensors` | `models/vae/` | 0.4GB |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `models/latent_upscale_models/` | 1.0GB |

3. After loading, change only three things: **UNET dropdown → nvfp4**, the prompt, and (flf2v) the two keyframe images. Keep every other template default (CFG=1, two-stage 9+3 distilled sigmas).
4. Templates also reference `gemma4_e2b_it_int8_convrot` (prompt rewriting) and a vocoder — if missing, just bypass those nodes; the main chain is unaffected.
5. Verify file sizes after download: the repo is gated, and an HTML error page silently saved as `.safetensors` is a classic failure mode.

## Batch / cloud automation (optional)

`precmd.sh` (RunPod boot: auto-upgrade ComfyUI + download models), `jobs.example.txt`, plus `ltx25_run.py` (direct-API runner) and `run_batch.sh` (per-shot download & verification) in the repo root.

---

## Five things the official library doesn't have (each packaged standalone)

| Package | Contents | Ready to use? |
|---|---|---|
| [`1-mshot/`](1-mshot/) | Multi-shot single generation: official t2v with length=241 + storyboard-prompt template | ✅ two edits |
| [`2-crossmodel-upscale/`](2-crossmodel-upscale/) | Any video → LTX latent 2× upscale (60s; beats Real-ESRGAN 8.8×) | ✅ one script + 2 models |
| [`3-m3-mlx/`](3-m3-mlx/) | Full recipe for LTX-2 on Apple Silicon (the `--low-ram` lifeline, etc.) | ✅ follow README |
| [`4-headless-batch/`](4-headless-batch/) | Unattended cloud batch: boot→upgrade→download→run→verify, three gates | needs RunPod |
| [`5-nvfp4-5090/`](5-nvfp4-5090/) | nvfp4 builds of the three official workflows (drag-in for 5090) + measured numbers | ✅ drag in |
