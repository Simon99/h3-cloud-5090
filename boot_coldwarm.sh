#!/usr/bin/env bash
# COLD-vs-WARM probe: 1 pod on the shared volume, sage 720P, generate 2 shots back-to-back.
# shot1 = cold (model load into VRAM), shot2 = warm. shot1 - shot2 = model-load penalty.
# Solo pod = zero volume contention. python3 -u + comfy.log give clean per-shot timing.
set -uo pipefail
ts(){ date +%s; }; t(){ date +%T; }
echo "[$(t)] CW_BOOT T=$(ts)"
C=/workspace/ComfyUI; OUT=/root/out; TMP=/root/tmp; PC=/root/pipcache
mkdir -p "$OUT" "$TMP" "$PC"
PIP="pip install --break-system-packages --cache-dir $PC -q"
$PIP -r "$C/requirements.txt" 2>&1 | tail -1
$PIP sageattention 2>&1 | tail -1
SAGE=""; python -c "import sageattention" 2>/dev/null && { SAGE="--use-sage-attention"; echo "[$(t)] SAGE_OK"; } || echo "[$(t)] SAGE_MISS"
echo "[$(t)] start ComfyUI $SAGE (out+temp local)"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory "$TMP" $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP ~$((i*3))s T=$(ts)"; break; }; sleep 3; done
echo "[$(t)] GEN_START T=$(ts)  (2 shots: shot1=cold, shot2=warm)"
# embedded 2-shot mode (no GSHOTS_FILE) -> water then forest, both 720P/141f/20step
cd /root && GSPECTRUM=0 GW=1312 GH=736 GF=141 GSTEPS=20 GN=2 python3 -u /root/cloud_gen.py
echo "[$(t)] per-shot (comfy.log): $(grep -a 'Prompt executed' /root/comfy.log | sed 's/.*executed in/#/' | tr '\n' ' ')"
echo "[$(t)] CW_DONE T=$(ts)"
