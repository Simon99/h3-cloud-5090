#!/usr/bin/env bash
# Provision the H3 worker: `provision.sh nodes` (custom nodes + patch) and/or `provision.sh models`.
# Idempotent: re-running skips what's present. Used at image-build and/or first-boot.
set -euo pipefail
COMFY=${COMFY:-/workspace/ComfyUI}
MODELS=${MODELS:-$COMFY/models}
CN=$COMFY/custom_nodes

install_nodes() {
  mkdir -p "$CN"; cd "$CN"
  clone() { [ -d "$(basename "$1" .git)" ] || git clone --depth 1 "$1"; }
  clone https://github.com/city96/ComfyUI-GGUF.git
  clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
  clone https://github.com/1038lab/ComfyUI-FlashVSR.git
  clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git
  clone https://github.com/kijai/ComfyUI-KJNodes.git
  # ComfyUI-Spectrum-MiniMax-H3 : add your source if used for accel
  for d in */requirements.txt; do pip install --no-cache-dir -r "$d" || true; done
  pip install --no-cache-dir diffusers peft rotary_embedding_torch omegaconf gguf || true
  # FlashVSR: block-sparse attn is unavailable/untested on RTX 40/50 -> force dense SDPA fallback
  F=$CN/ComfyUI-FlashVSR/FlashVSR/models/wan_video_dit.py
  [ -f "$F" ] && sed -i 's/\(def flash_attention(.*compatibility_mode=\)False/\1True/' "$F" && echo "[patch] FlashVSR compatibility_mode=True"
  echo "[provision] nodes done"
}

dl() { # repo file dest_subdir  — download ONCE to the HF cache (on the volume) + symlink into models/.
  local repo="$1" file="$2" sub="$3"; mkdir -p "$MODELS/$sub"
  local name; name=$(basename "$file")
  [ -e "$MODELS/$sub/$name" ] && { echo "  have $name"; return; }
  echo "  fetch $repo :: $name"
  HF_HUB_ENABLE_HF_TRANSFER=1 python -c "
from huggingface_hub import hf_hub_download
import os
p = hf_hub_download('$repo', '$file')          # lands in \$HF_HOME cache (on the volume)
d = os.path.join('$MODELS', '$sub', '$name')
try: os.remove(d)
except FileNotFoundError: pass
os.symlink(p, d)                                # models/ holds a symlink, not a 2nd copy
" || echo "  !! failed: $name"
}

install_models() {
  # keep the HF cache on the same disk as models (the volume) so we never double-store 65GB.
  export HF_HOME="${HF_HOME:-$COMFY/../.hfcache}"; mkdir -p "$HF_HOME"
  echo "[provision] HF cache -> $HF_HOME ; models (symlinks) -> $MODELS"
  # --- MiniMax-H3 (paths verified vs Comfy-Org/MiniMax-H3 tree; 5090 => nvfp4 encoder + fp8 diffusion) ---
  local H3=Comfy-Org/MiniMax-H3
  dl $H3 diffusion_models/minimax_h3_ref2va_pruned_fp8_scaled.safetensors diffusion_models
  dl $H3 diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors  diffusion_models
  dl $H3 text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors        text_encoders
  dl $H3 vae/minimax_h3_video_vae_fp16.safetensors                         vae
  dl $H3 vae/minimax_h3_audio_vae_fp32.safetensors                         vae
  # --- FlashVSR: node auto-downloads on first run via hf_hub_download; we warm the HF cache with the
  #     REAL repo files (verified vs 1038lab/FlashVSR tree) so that first run is instant. ---
  local FV=1038lab/FlashVSR
  for f in FlashVSR1_1.safetensors Wan2_1-T2V-1_3B_FlashVSR_fp32.safetensors Wan2.1_VAE.safetensors \
           TCDecoder.safetensors LQ_proj_in.safetensors Wan2_1_FlashVSR_LQ_proj_model_bf16.safetensors Prompt.safetensors; do
    dl $FV "$f" FlashVSR
  done
  # --- SeedVR2 (32GB can use fp16; Q4 gguf also fine) ---
  dl AInVFX/SeedVR2_comfyUI seedvr2_ema_3b-Q4_K_M.gguf     SEEDVR2
  dl numz/SeedVR2_comfyUI   ema_vae_fp16.safetensors        SEEDVR2
  # --- Real-ESRGAN (upscale finals / legacy 544p) ---
  mkdir -p "$MODELS/upscale_models"
  for u in RealESRGAN_x4plus.pth realesr-general-x4v3.pth; do
    [ -f "$MODELS/upscale_models/$u" ] || curl -fsSL -o "$MODELS/upscale_models/$u" \
      "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/$u" || true
  done
  echo "[provision] models done ($(du -sh $MODELS | cut -f1))"
}

case "${1:-all}" in
  nodes)  install_nodes ;;
  models) install_models ;;
  all)    install_nodes; install_models ;;
  *) echo "usage: provision.sh [nodes|models|all]"; exit 1 ;;
esac
