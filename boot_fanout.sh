#!/usr/bin/env bash
# LEAN fan-out gen pod (NO network volume): clone base ComfyUI (has native H3 nodes),
# download ONLY the 4 H3 gen models (~33GB, skips the 32GB of upscaling models),
# install SageAttention, start ComfyUI --use-sage-attention, generate 1 sage 720P shot.
# Timestamps every phase so the orchestrator can measure DL vs boot vs gen.
set -uo pipefail
ts(){ date +%s; }; t(){ date +%T; }
echo "[$(t)] FANOUT_BOOT T=$(ts)"
C=/workspace/ComfyUI
PIP="pip install --break-system-packages -q"   # RunPod img is PEP-668 externally-managed

# 1. base ComfyUI (native H3 support: MiniMaxH3ImageToVideo / VAEDecodeAudio / CLIPLoader minimax)
if [ ! -f "$C/main.py" ]; then echo "[$(t)] clone ComfyUI"; git clone --depth 1 -q https://github.com/comfyanonymous/ComfyUI.git "$C"; fi
echo "[$(t)] pip reqs"; $PIP -r "$C/requirements.txt" 2>&1 | tail -1
$PIP huggingface_hub hf_transfer sageattention 2>&1 | tail -1
SAGE=""; python -c "import sageattention" 2>/dev/null && { SAGE="--use-sage-attention"; echo "[$(t)] SAGE_OK"; } || echo "[$(t)] SAGE_MISS"

# 2. download the 4 H3 gen models (~33GB) straight into models/ (subdir preserved by local_dir)
echo "[$(t)] DL_START T=$(ts)"
HF_HUB_ENABLE_HF_TRANSFER=1 python - <<'PY'
from huggingface_hub import hf_hub_download
R="Comfy-Org/MiniMax-H3"; D="/workspace/ComfyUI/models"
for f in ["diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
          "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
          "vae/minimax_h3_video_vae_fp16.safetensors",
          "vae/minimax_h3_audio_vae_fp32.safetensors"]:
    hf_hub_download(R, f, local_dir=D); print("  got", f, flush=True)
PY
echo "[$(t)] DL_DONE T=$(ts)  models=$(du -sh $C/models 2>/dev/null | cut -f1)"

# 3. ComfyUI up
echo "[$(t)] start ComfyUI $SAGE"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 $SAGE > /workspace/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP ~$((i*3))s T=$(ts)"; break; }; sleep 3; done

# 4. generate one sage-only 720P shot (GTAG/GSEED injected per-pod by the orchestrator)
echo "[$(t)] GEN_START T=$(ts)"
cd /workspace/h && GSPECTRUM=0 GW=1312 GH=736 GF=141 GSTEPS=20 GN=1 python3 cloud_gen.py
echo "[$(t)] FANOUT_DONE T=$(ts)"
