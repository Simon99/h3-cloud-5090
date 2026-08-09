#!/usr/bin/env bash
# One-shot: deploy a fresh 5090 (with SSH key) + attach the volume -> boot (pip deps + ComfyUI)
# -> generate 2 bear shots -> collect timings -> ALWAYS terminate (even on error/ctrl-C).
# Needs ~/.runpod-key and ~/.ssh/id_rsa (+ its .pub added to the RunPod account).
set -uo pipefail
K=$(cat ~/.runpod-key)
PUB=$(cat ~/.ssh/id_rsa.pub)
VOL=ufj8mzg8uq
IMG="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
api(){ curl -s -m40 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }
POD=""
cleanup(){ [ -n "$POD" ] && { echo "[cleanup] terminating $POD"; api -X DELETE "https://rest.runpod.io/v1/pods/$POD" -o /dev/null -w " HTTP %{http_code}\n"; }; }
trap cleanup EXIT INT TERM

echo "[1] deploy 5090 + volume + SSH key ..."
POD=$(api -X POST https://rest.runpod.io/v1/pods -d "$(python3 -c "import json,os;print(json.dumps({
 'name':'bear-test','imageName':'$IMG','gpuTypeIds':['NVIDIA GeForce RTX 5090'],'gpuCount':1,
 'networkVolumeId':'$VOL','containerDiskInGb':40,'ports':['8188/http','22/tcp'],'dataCenterIds':['EUR-IS-1'],
 'computeType':'GPU','env':{'PUBLIC_KEY':'''$PUB'''}}))")" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
[ -z "$POD" ] && { echo "deploy failed"; exit 1; }
echo "    pod=$POD"

echo "[2] wait for runtime (image pull + volume mount, up to ~8 min) ..."
IP=""; SPORT=""
for i in $(seq 1 48); do
  J=$(api "https://rest.runpod.io/v1/pods/$POD")
  read RT IP SPORT < <(echo "$J" | python3 -c "import sys,json;d=json.load(sys.stdin);pm=d.get('portMappings') or {};print('yes' if d.get('runtime') else 'no', d.get('publicIp') or '-', pm.get('22') or '-')")
  echo "    [$i] runtime=$RT ip=$IP sshport=$SPORT"
  [ "$IP" != "-" ] && [ "$SPORT" != "-" ] && break   # SSH endpoint ready is enough (runtime flag often never flips)
  sleep 12
done
[ "$IP" = "-" ] && { echo "runtime/SSH not ready"; exit 1; }

SSH="ssh -i $HOME/.ssh/id_rsa -p $SPORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes root@$IP"
echo "[3] wait for sshd @ $IP:$SPORT ..."
for i in $(seq 1 30); do $SSH 'echo ok' >/dev/null 2>&1 && { echo "    sshd up"; break; }; sleep 8; done

echo "[4] boot: pull repo + pip deps + ComfyUI + 2 shots (detached) ..."
$SSH 'cd /workspace/h && git pull -q; setsid bash /workspace/h/boot.sh >/workspace/boot.log 2>&1 </dev/null & echo launched' 2>&1 | tail -1

echo "[5] monitor boot.log until BOOT_DONE (~15-25 min) ..."
for i in $(seq 1 90); do
  L=$($SSH 'tail -3 /workspace/boot.log 2>/dev/null' 2>/dev/null | tr -d '\r')
  echo "$L" | grep -aE "BOOT|COMFY_UP|SHOT_START|SHOT_DONE|RUN_ERR|SUBMIT_ERR|pip" | tail -1
  echo "$L" | grep -qa "BOOT_DONE" && { echo "=== BOOT_DONE ==="; break; }
  sleep 20
done

echo "[6] FULL boot.log (captures gen errors before terminate):"
echo "-------------------- boot.log --------------------"
$SSH 'cat /workspace/boot.log' 2>/dev/null | tr -d '\r' | tail -80
echo "--------------------------------------------------"

echo "[7] pull the 2 output videos via ComfyUI HTTP proxy ..."
mkdir -p ~/claude-sandboxes/director/cloud-5090/bear_cloud_out
BASE="https://${POD}-8188.proxy.runpod.net"
for f in $($SSH 'ls /workspace/ComfyUI/output/video/ 2>/dev/null | grep cloudtest' 2>/dev/null | tr -d '\r'); do
  curl -s -m120 "$BASE/view?filename=$f&subfolder=video&type=output" -o ~/claude-sandboxes/director/cloud-5090/bear_cloud_out/"$f" && echo "  got $f"
done
echo "[done] (pod will auto-terminate on exit)"
