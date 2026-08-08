#!/usr/bin/env bash
# Pod entrypoint: ensure models present (if not baked / on a mounted volume), then run ComfyUI.
set -euo pipefail
COMFY=${COMFY:-/workspace/ComfyUI}
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False

# If models weren't baked and aren't on a mounted volume, fetch them now (first boot ~5-10 min).
if [ ! -f "$COMFY/models/vae/minimax_h3_video_vae_fp16.safetensors" ]; then
  echo "[worker] models missing -> provisioning"
  bash /workspace/provision.sh models
fi

cd "$COMFY"
# --listen 0.0.0.0 so RunPod's proxy (https://<pod>-8188.proxy.runpod.net) can reach it.
# 5090 has 32GB: no --reserve-vram needed for H3; sage attention optional.
exec python main.py --listen 0.0.0.0 --port 8188 --use-sage-attention
