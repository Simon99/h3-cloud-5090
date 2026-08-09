#!/usr/bin/env bash
# Fresh-pod boot: reinstall pip deps (container fresh; ComfyUI+models persist on the volume), start ComfyUI, run gen.
set -uo pipefail
PC=/workspace/.pipcache; mkdir -p "$PC"
echo "[$(date +%T)] BOOT pip deps (fresh container)"
pip install --cache-dir "$PC" -q -r /workspace/ComfyUI/requirements.txt 2>&1 | tail -1
for r in /workspace/ComfyUI/custom_nodes/*/requirements.txt; do pip install --cache-dir "$PC" -q -r "$r" 2>&1 | tail -1; done
pip install --cache-dir "$PC" -q diffusers peft rotary_embedding_torch omegaconf gguf imageio-ffmpeg 2>&1 | tail -1
echo "[$(date +%T)] BOOT start ComfyUI"
nohup python /workspace/ComfyUI/main.py --listen 0.0.0.0 --port 8188 > /workspace/comfy.log 2>&1 &
for i in $(seq 1 45); do curl -s -m3 localhost:8188/system_stats >/dev/null 2>&1 && { echo "[$(date +%T)] COMFY_UP"; break; }; sleep 4; done
echo "[$(date +%T)] BOOT run cloud_gen (2 shots)"
python3 /workspace/h/cloud_gen.py
echo "[$(date +%T)] BOOT_DONE"
