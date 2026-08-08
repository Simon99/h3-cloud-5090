#!/usr/bin/env bash
# Build (and optionally push) the worker image.
#   BAKE=1 (default): download all ~65GB models INTO the image -> ~70GB image, ~$0/月 storage,
#                     每次開機拉映像(host 有 cache 就快),不用 volume、不用開機從 HF 下載。
#   BAKE=0          : lean image (~3GB);模型於首次開機由 worker_start.sh 從 HF 下載。
#
# ⚠️ Baking 會在 build 時從 HF 下 65GB、再 push ~70GB → 建議在「網路快的機器/便宜雲實例」上 build，
#    不要在家用小頻寬 build。RunPod host 會 cache 映像,重複用同一台就快。
#
# 用法:
#   ./build_image.sh youruser/h3-worker:1            # bake + 只 build
#   PUSH=1 ./build_image.sh youruser/h3-worker:1     # bake + build + push（需先 docker login）
#   BAKE=0 PUSH=1 ./build_image.sh youruser/h3-worker:1   # lean 版
set -euo pipefail
IMG=${1:?usage: [BAKE=1] [PUSH=1] ./build_image.sh <registry/user/image:tag>}
BAKE=${BAKE:-1}; PUSH=${PUSH:-0}
echo "[build] $IMG  (BAKE_MODELS=$BAKE)"
docker build -t "$IMG" --build-arg BAKE_MODELS="$BAKE" .
echo "[build] size: $(docker images "$IMG" --format '{{.Size}}')"
if [ "$PUSH" = "1" ]; then
  echo "[push] $IMG (make sure you've: docker login <registry>)"
  docker push "$IMG"
  echo "[push] done -> 在 RunPod/Vast template 指定這個映像即可"
else
  echo "[hint] 要上傳:PUSH=1 再跑一次,或手動 docker push $IMG"
fi
