#!/usr/bin/env bash
# v5 boot: models from HF (proven fast+resumable globally). Optional HF_TOKEN lifts parallel limits.
# Env: MODEL_SET=fl2va|ref2va|both  GTURBO=1(LoRA)  GN>0 run cloud_gen  HF_TOKEN(optional)
set -uo pipefail
t(){ date +%T; }
echo "[$(t)] V5_BOOT"
C=/workspace/ComfyUI; OUT=/root/out; mkdir -p "$OUT" /root/tmp
export HF_TOKEN=${HF_TOKEN:-}
MODEL_SET=${MODEL_SET:-fl2va}
echo "[$(t)] DL_START set=$MODEL_SET token=$([ -n "$HF_TOKEN" ] && echo yes || echo no)"
python - <<PY
import os
from huggingface_hub import hf_hub_download
tok=os.environ.get("HF_TOKEN") or None
D="$C/models"; ms="$MODEL_SET"
files=["text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
       "vae/minimax_h3_video_vae_fp16.safetensors","vae/minimax_h3_audio_vae_fp32.safetensors"]
if ms in ("fl2va","both"): files.insert(0,"diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors")
if ms in ("ref2va","both"): files.insert(0,"diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors")
for f in files:
    if os.path.exists(os.path.join(D,f)): print("  have",f,flush=True); continue
    hf_hub_download("Comfy-Org/MiniMax-H3",f,local_dir=D,token=tok); print("  got",f,flush=True)
PY
if [ "${GTURBO:-0}" = 1 ]; then
  L=${GTURBO_LORA:-minimax_h3_turbo_v4_step600_ema.safetensors}
  [ -f "$C/models/loras/$L" ] || python -c "import os;from huggingface_hub import hf_hub_download;hf_hub_download('larryvrh/MiniMax-H3-Turbo-Lora','$L',local_dir='$C/models/loras',token=os.environ.get('HF_TOKEN') or None)"
  echo "[$(t)] LORA_READY $L"
fi
echo "[$(t)] DL_DONE $(du -sh $C/models|cut -f1)"
SAGE=""; python -c "import sageattention" 2>/dev/null && SAGE="--use-sage-attention"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory /root/tmp $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP"; break; }; sleep 3; done
if [ "${GN:-0}" -gt 0 ]; then cd /workspace/h && python3 -u cloud_gen.py; fi
echo "[$(t)] V5_READY"
