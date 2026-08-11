#!/usr/bin/env python3
# 下載 H3 生成需要的 4 個模型檔到 ComfyUI/models(供 Dockerfile.baked 在 build 時烤入)。
from huggingface_hub import hf_hub_download
import os
R = "Comfy-Org/MiniMax-H3"
D = "/workspace/ComfyUI/models"
DIT = os.environ.get("DIT_FILE", "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors")
for f in [
    DIT,
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
]:
    p = hf_hub_download(R, f, local_dir=D)
    print("baked", f, flush=True)
