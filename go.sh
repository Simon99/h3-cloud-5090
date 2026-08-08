#!/usr/bin/env bash
# First-run orchestrator on a fresh RunPod 5090 pod.
# Launch detached:  setsid bash /workspace/h/go.sh >/workspace/setup.log 2>&1 </dev/null &
set -uo pipefail
cd "$(dirname "$0")"
echo "[$(date +%T)] === go.sh START ==="
echo "[$(date +%T)] STEP torch check"
python -c "import torch;print('TORCH', torch.__version__, torch.cuda.get_device_name(0))" || { echo "TORCH FAIL"; exit 1; }
echo "[$(date +%T)] STEP provision nodes"
bash provision.sh nodes
echo "[$(date +%T)] STEP start ComfyUI :8188"
nohup python /workspace/ComfyUI/main.py --listen 0.0.0.0 --port 8188 >/workspace/comfy.log 2>&1 &
sleep 6
echo "[$(date +%T)] STEP provision models (~15-40 min)"
bash provision.sh models
echo "[$(date +%T)] === ALLDONE ==="
