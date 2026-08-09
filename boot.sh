#!/usr/bin/env bash
# Fresh-pod boot: reinstall pip deps (container fresh; ComfyUI+models persist on the volume), start ComfyUI, run gen.
set -uo pipefail
PC=/workspace/.pipcache; mkdir -p "$PC"
PIP="pip install --break-system-packages --cache-dir $PC -q"   # --break-system-packages: RunPod img is PEP-668 externally-managed
echo "[$(date +%T)] BOOT pip deps (fresh container)"
$PIP -r /workspace/ComfyUI/requirements.txt 2>&1 | tail -2
for r in /workspace/ComfyUI/custom_nodes/*/requirements.txt; do $PIP -r "$r" 2>&1 | tail -1; done
$PIP diffusers peft rotary_embedding_torch omegaconf gguf imageio-ffmpeg 2>&1 | tail -1
echo "[$(date +%T)] BOOT start ComfyUI"
nohup python /workspace/ComfyUI/main.py --listen 0.0.0.0 --port 8188 > /workspace/comfy.log 2>&1 &
echo "[$(date +%T)] BOOT wait ComfyUI ready (up to ~10 min; custom-node imports are slow)"
UP=0
for i in $(seq 1 120); do
  curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { UP=1; echo "[$(date +%T)] COMFY_UP after ~$((i*5))s"; break; }
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$(date +%T)] COMFY_FAILED to start — comfy.log tail:"; tail -30 /workspace/comfy.log; echo "[$(date +%T)] BOOT_DONE"; exit 1
fi
echo "[$(date +%T)] BOOT run cloud_gen"
python3 /workspace/h/cloud_gen.py
echo "[$(date +%T)] BOOT_DONE"
