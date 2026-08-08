#!/usr/bin/env bash
# Optional convenience: spin up / list / kill a pool of 5090 pods and emit workers.txt.
# Needs: runpodctl (https://github.com/runpod/runpodctl) configured with your API key,
# and a pod TEMPLATE built from the Dockerfile here (or your pushed image).
# Verify runpodctl flags against your version — API surfaces change.
set -euo pipefail
CMD=${1:-help}; N=${2:-4}
TEMPLATE_ID=${RUNPOD_TEMPLATE_ID:-"REPLACE_ME"}   # your pod template (image + 8188 exposed)
GPU=${RUNPOD_GPU:-"NVIDIA GeForce RTX 5090"}
NAME=${RUNPOD_NAME:-h3worker}

case "$CMD" in
  up)
    : > workers.txt
    for i in $(seq 1 "$N"); do
      # create an on-demand pod from the template; capture its id
      id=$(runpodctl create pod --name "${NAME}-$i" --templateId "$TEMPLATE_ID" \
             --gpuType "$GPU" --gpuCount 1 --ports "8188/http" 2>/dev/null \
             | grep -oE 'pod "[a-z0-9]+"' | grep -oE '[a-z0-9]+"$' | tr -d '"') || true
      [ -n "${id:-}" ] && echo "https://${id}-8188.proxy.runpod.net" >> workers.txt
      echo "started ${NAME}-$i -> ${id:-FAILED}"
    done
    echo "--- workers.txt ---"; cat workers.txt
    echo "give pods ~1-2 min (or 5-10 if downloading models on first boot) before running controller"
    ;;
  down) runpodctl get pod | grep "$NAME" | awk '{print $1}' | xargs -r -n1 runpodctl remove pod ;;
  ls)   runpodctl get pod | grep "$NAME" || echo "(none)" ;;
  *) echo "usage: RUNPOD_TEMPLATE_ID=xxx ./runpod_pool.sh up <N> | down | ls" ;;
esac
