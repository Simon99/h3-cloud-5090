#!/usr/bin/env bash
# Volume-mounted fan-out gen pod: models + ComfyUI code READ from the shared network volume
# (/workspace, multi-attached), ALL writes go to LOCAL container disk (/root) to avoid
# cross-pod write contention. sage-only 720P. Timestamps each phase.
set -uo pipefail
ts(){ date +%s; }; t(){ date +%T; }
echo "[$(t)] VOLBOOT T=$(ts)"
C=/workspace/ComfyUI                       # shared volume: models + code (READ)
OUT=/root/out; TMP=/root/tmp; PC=/root/pipcache   # local disk (WRITE) — no cross-pod clash
mkdir -p "$OUT" "$TMP" "$PC"
PIP="pip install --break-system-packages --cache-dir $PC -q"

echo "[$(t)] pip reqs (fresh container; models already on volume)"
$PIP -r "$C/requirements.txt" 2>&1 | tail -1
$PIP sageattention 2>&1 | tail -1
SAGE=""; python -c "import sageattention" 2>/dev/null && { SAGE="--use-sage-attention"; echo "[$(t)] SAGE_OK"; } || echo "[$(t)] SAGE_MISS"

echo "[$(t)] models on volume: $(ls $C/models/diffusion_models/*.safetensors 2>/dev/null | wc -l) diffusion, $(ls $C/models/text_encoders/*.safetensors 2>/dev/null | wc -l) clip, $(ls $C/models/vae/*.safetensors 2>/dev/null | wc -l) vae"
echo "[$(t)] start ComfyUI $SAGE (out+temp local)"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory "$TMP" $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP ~$((i*3))s T=$(ts)"; break; }; sleep 3; done

echo "[$(t)] GEN_START T=$(ts) GSHOTS=${GSHOTS:-all}"
[ -f /root/cloud_gen.py ] || cp /workspace/h/cloud_gen.py /root/cloud_gen.py 2>/dev/null || true   # fallback to volume copy
cd /root && GSPECTRUM=0 GSHOTS_FILE=/root/bear_shots.txt GSHOTS="${GSHOTS:-}" \
  GW=1312 GH=736 GF=141 GSTEPS=20 python3 /root/cloud_gen.py
echo "[$(t)] outputs: $(ls $OUT/*.mp4 2>/dev/null | wc -l) mp4"
echo "[$(t)] VOLBOOT_DONE T=$(ts)"
