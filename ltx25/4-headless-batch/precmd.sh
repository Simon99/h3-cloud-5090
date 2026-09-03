#!/bin/bash
# LTX-2.5 pod 前置腳本(RunPod 容器內執行;需 env HF_TOKEN)
# 用法(搭配本 repo runpod.py):python3 runpod.py create --precmd="$(cat ltx25/precmd.sh)"
# ① ComfyUI 升級到 0.34.3 —— 用 codeload tarball,避開機房 git 限流
echo PRE_START
for i in 1 2 3; do
  curl -sL https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/v0.34.3 -o /tmp/c.tgz \
    && [ $(stat -c %s /tmp/c.tgz) -gt 5000000 ] && break
  echo TGZ_RETRY_$i; sleep 5
done
tar xzf /tmp/c.tgz -C /tmp && cp -a /tmp/ComfyUI-0.34.3/. /workspace/ComfyUI/ && echo UPGRADE_COPIED
cd /workspace/ComfyUI && python -m pip install -q -r requirements.txt && echo PIP_OK
python -c "import torch; print('TORCH_'+torch.__version__)"   # 驗 torch 沒被動到
# ② 模型五檔並行下載 + 逐檔大小 gate(防 LFS 指標/錯誤頁存成 .safetensors)
M=/workspace/ComfyUI/models
mkdir -p $M/diffusion_models $M/text_encoders $M/vae $M/latent_upscale_models
dl(){ for i in 1 2 3; do
  curl -sL -H "Authorization: Bearer $HF_TOKEN" "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/$1" -o "$M/$1" \
    && [ $(stat -c %s "$M/$1") -ge $2 ] && echo DL_OK_$(basename $1) && return 0
  echo DL_RETRY_$(basename $1)_$i; sleep 5
done; echo DL_FAIL_$(basename $1); }
dl diffusion_models/ltx-2.5-22b-distilled-transformer-nvfp4.safetensors 18000000000 &
dl text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors 15000000000 &
dl vae/ltx-2.5-video-vae-conv-bf16.safetensors 1400000000 &
dl vae/ltx-2.5-audio-vae-bf16.safetensors 300000000 &
dl latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors 900000000 &
wait
echo LTX_PRE_DONE
