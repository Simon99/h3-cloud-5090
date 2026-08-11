#!/usr/bin/env bash
# v3 boot: models fetched from OUR GHCR blob (the v2 image's model layer, 38.3GB tar.gz)
# via resumable ranged download — no docker-layer fragility, no HF rate limits.
# Env: GTURBO=1(get LoRA)  GN>0(run cloud_gen after)  MODELS_BLOB/MODELS_SIZE override.
set -uo pipefail
t(){ date +%T; }
echo "[$(t)] V3_BOOT"
C=/workspace/ComfyUI; OUT=/root/out; mkdir -p "$OUT" /root/tmp
BLOB=${MODELS_BLOB:-sha256:c02523dcf556affd4cda700d79cfda89c88a7fadd127a55a35d1c3cf8e4ad964}
SIZE=${MODELS_SIZE:-38294492166}
DIT="$C/models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"

if [ ! -f "$DIT" ]; then
  TGZ=/workspace/models_layer.tgz
  echo "[$(t)] BLOB_DL_START (GHCR, resumable)"
  for try in $(seq 1 30); do
    have=$(stat -c%s "$TGZ" 2>/dev/null || echo 0)
    [ "$have" -ge "$SIZE" ] && break
    TOK=$(curl -s "https://ghcr.io/token?scope=repository:simon99/h3-gen:pull" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
    # resolve the short-lived signed URL, then resume with aria2c (16 conn) or curl -C -
    URL=$(curl -s -o /dev/null -w '%{redirect_url}' -H "Authorization: Bearer $TOK" "https://ghcr.io/v2/simon99/h3-gen/blobs/$BLOB")
    if command -v aria2c >/dev/null 2>&1; then
      aria2c -c -x16 -s16 -k4M --file-allocation=none -d "$(dirname $TGZ)" -o "$(basename $TGZ)" "$URL" >/dev/null 2>&1 || true
    else
      curl -sL -C - -o "$TGZ" "$URL" || true
    fi
    echo "[$(t)] blob try#$try: $(stat -c%s "$TGZ" 2>/dev/null || echo 0)/$SIZE"
  done
  have=$(stat -c%s "$TGZ" 2>/dev/null || echo 0)
  if [ "$have" -ge "$SIZE" ]; then
    echo "[$(t)] BLOB_DL_DONE, extracting"
    tar xzf "$TGZ" -C / && rm -f "$TGZ"
    echo "[$(t)] EXTRACT_DONE $(du -sh $C/models 2>/dev/null|cut -f1)"
  else
    echo "[$(t)] BLOB_FAILED -> HF fallback"
    python - <<'PY'
import os
from huggingface_hub import hf_hub_download
D="/workspace/ComfyUI/models"
for f in ["diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
          "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
          "vae/minimax_h3_video_vae_fp16.safetensors","vae/minimax_h3_audio_vae_fp32.safetensors"]:
    d=os.path.join(D,f)
    if not os.path.exists(d): hf_hub_download("Comfy-Org/MiniMax-H3",f,local_dir=D); print("  got",f,flush=True)
PY
  fi
else
  echo "[$(t)] models present, skip download"
fi

if [ "${GTURBO:-0}" = 1 ]; then
  L=${GTURBO_LORA:-minimax_h3_turbo_v4_step600_ema.safetensors}
  [ -f "$C/models/loras/$L" ] || python -c "from huggingface_hub import hf_hub_download;hf_hub_download('larryvrh/MiniMax-H3-Turbo-Lora','$L',local_dir='$C/models/loras')"
  echo "[$(t)] LORA_READY $L"
fi
SAGE=""; python -c "import sageattention" 2>/dev/null && SAGE="--use-sage-attention"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory /root/tmp $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP"; break; }; sleep 3; done
if [ "${GN:-0}" -gt 0 ]; then cd /workspace/h && python3 -u cloud_gen.py; fi
echo "[$(t)] V3_READY"
