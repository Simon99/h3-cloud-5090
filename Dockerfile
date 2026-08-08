# MiniMax-H3 + upscaling worker for RTX 5090 (Blackwell / sm_120).
# Blackwell REQUIRES CUDA 12.8+ / PyTorch cu128 — older images fail with "sm_120 not supported".
# Build lean (models fetched at first boot) OR bake models in with --build-arg BAKE_MODELS=1.
#
#   docker build -t youruser/h3-worker:1 .
#   docker build -t youruser/h3-worker-baked:1 --build-arg BAKE_MODELS=1 .   # ~70GB image
#   docker push youruser/h3-worker:1
#
# Verify the base tag is a current cu128 build before pinning in production.
ARG BASE=pytorch/pytorch:2.7.1-cuda12.8-cudnn9-devel
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    COMFY=/workspace/ComfyUI MODELS=/workspace/ComfyUI/models \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False
RUN apt-get update && apt-get install -y git ffmpeg curl aria2 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git $COMFY
RUN pip install --no-cache-dir -r $COMFY/requirements.txt "huggingface_hub[hf_transfer]" imageio-ffmpeg

# Custom nodes (generation + upscaling) + the FlashVSR block-sparse -> SDPA patch
COPY provision.sh worker_start.sh /workspace/
RUN bash /workspace/provision.sh nodes

# Optional: bake all model weights into the image (else first-boot downloads them)
ARG BAKE_MODELS=0
ENV HF_HUB_ENABLE_HF_TRANSFER=1
RUN if [ "$BAKE_MODELS" = "1" ]; then bash /workspace/provision.sh models; fi

EXPOSE 8188
CMD ["bash", "/workspace/worker_start.sh"]
