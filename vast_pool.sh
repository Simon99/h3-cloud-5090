#!/usr/bin/env bash
# Vast.ai fan-out pool: search verified RTX 5090 offers, launch N, emit workers.txt.
# Setup:  pip install vastai  &&  vastai set api-key <YOUR_KEY>
# Verify flags against your vastai version (CLI evolves). Needs jq.
# Vast maps container port 8188 to a host port; we read the public ip+port back per instance.
set -euo pipefail
CMD=${1:-help}; N=${2:-4}
IMAGE=${VAST_IMAGE:-"YOURUSER/h3-worker:1"}    # your pushed baked image (models inside)
DISK=${VAST_DISK:-80}
LABEL=${VAST_LABEL:-h3worker}
# ComfyUI must listen on 0.0.0.0:8188 (worker_start.sh does). -p exposes it.
ONSTART='bash /workspace/worker_start.sh'

case "$CMD" in
  up)
    echo "[vast] searching verified RTX 5090 offers (cheapest first)..."
    # rentable + verified + 1x 5090, sort by \$/hr ascending; take N offer ids
    offers=$(vastai search offers \
      "gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>=$DISK" \
      -o 'dph+' --raw | jq -r '.[].id' | head -n "$N")
    [ -z "$offers" ] && { echo "no verified 5090 offers in stock right now"; exit 1; }
    : > workers.txt
    for oid in $offers; do
      echo "[vast] create on offer $oid"
      vastai create instance "$oid" --image "$IMAGE" --disk "$DISK" \
        --onstart-cmd "$ONSTART" --label "$LABEL" -p 8188:8188 >/dev/null || { echo "  create failed"; continue; }
    done
    echo "[vast] waiting for instances to boot + map ports (~1-3 min; longer if downloading models)..."
    sleep 60
    # collect public ip:port for internal 8188 of our labelled instances
    vastai show instances --raw | jq -r --arg L "$LABEL" '
      .[] | select(.label==$L) |
      (.public_ipaddr) as $ip |
      (.ports["8188/tcp"][0].HostPort // empty) as $p |
      select($ip and $p) | "http://\($ip):\($p)"' | tee workers.txt
    echo "--- workers.txt ---"; cat workers.txt
    echo "if empty: give it more time, then re-run: $0 urls"
    ;;
  urls)  # re-emit workers.txt once ports are mapped
    vastai show instances --raw | jq -r --arg L "$LABEL" '
      .[] | select(.label==$L) | (.public_ipaddr) as $ip |
      (.ports["8188/tcp"][0].HostPort // empty) as $p |
      select($ip and $p) | "http://\($ip):\($p)"' | tee workers.txt ;;
  ls)    vastai show instances | grep "$LABEL" || echo "(none)" ;;
  down)  vastai show instances --raw | jq -r --arg L "$LABEL" '.[]|select(.label==$L)|.id' \
           | xargs -r -n1 vastai destroy instance ;;
  *) echo "usage: VAST_IMAGE=you/h3-worker:1 ./vast_pool.sh up <N> | urls | ls | down" ;;
esac
