#!/usr/bin/env bash
# Baked-image boot:模型已在 image 裡,只需啟 ComfyUI + 生成。無下載、無 volume → 秒進。
set -uo pipefail
ts(){ date +%s; }; t(){ date +%T; }
echo "[$(t)] BAKED_BOOT T=$(ts)"
C=/workspace/ComfyUI; OUT=/root/out; mkdir -p "$OUT" /root/tmp
SAGE=""; python -c "import sageattention" 2>/dev/null && { SAGE="--use-sage-attention"; echo "[$(t)] SAGE_OK"; }
# turbo LoRA:不烤進映像(迭代快),要用時開機抓 780MB(幾十秒)
if [ "${GTURBO:-0}" = 1 ]; then
  L=${GTURBO_LORA:-minimax_h3_turbo_v4_step600_ema.safetensors}
  [ -f "$C/models/loras/$L" ] || python - <<PY
from huggingface_hub import hf_hub_download
hf_hub_download("larryvrh/MiniMax-H3-Turbo-Lora","$L",local_dir="$C/models/loras")
print("lora downloaded", flush=True)
PY
  echo "[$(t)] LORA_READY $L"
fi
echo "[$(t)] models: $(ls $C/models/diffusion_models/*.safetensors 2>/dev/null|wc -l) diffusion, $(ls $C/models/text_encoders/*.safetensors 2>/dev/null|wc -l) clip, $(ls $C/models/vae/*.safetensors 2>/dev/null|wc -l) vae"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory /root/tmp $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP ~$((i*3))s T=$(ts)"; break; }; sleep 3; done
echo "[$(t)] GEN_START T=$(ts)"
cd /workspace/h && GSPECTRUM=0 GW=${GW:-1312} GH=${GH:-736} GF=${GF:-141} GSTEPS=${GSTEPS:-20} GN=${GN:-1} GSHOTS_FILE=${GSHOTS_FILE:-} GSHOTS=${GSHOTS:-} python3 -u cloud_gen.py
echo "[$(t)] per-shot: $(grep -a 'Prompt executed' /root/comfy.log|tail -1)"
echo "[$(t)] BAKED_DONE T=$(ts)"
