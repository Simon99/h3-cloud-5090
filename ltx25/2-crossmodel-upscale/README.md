# Pkg 2 | Cross-model upscale: any video → LTX latent 2× (no official cross-family combo)

[中文版 →](README.zh.md)

Use LTX's latent spatial upscaler on **another model's output** (we use it on MiniMax-H3's 544P):
`any mp4 → VAEEncode (LTX VAE) → LTXVLatentUpsampler 2× → VAEDecode → 1920×1088`

Runner: `ltx_up.py <input.mp4> [output_prefix]` (hits a local ComfyUI API on :8189).
Only two models needed: LTX video VAE (1.5GB) + spatial upscaler (1.0GB). Runs on an 8GB card.

Measured comparison (960×544 → 1920×1088):
| Method | Time | Look |
|---|---|---|
| **LTX latent 2×** | **60s** | clean, no halos |
| Real-ESRGAN | 526s | digital halos + plastic skin |

Why it matters: H3 generates at the same speed at 544P and 480P (fixed-overhead plateau), so
"cloud 544P + local LTX upscale" is faster than direct 736P cloud generation, ends up at a higher
resolution, and avoids the high-res VAE decode that can kill ComfyUI.
Note: `_pick_upscaler()` selects the upscaler from the enum at runtime — hard-coded filenames broke three times across versions.
