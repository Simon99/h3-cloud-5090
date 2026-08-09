#!/usr/bin/env bash
# Fan-out speed test: deploy N lean 5090 pods (no volume), each downloads H3 gen models +
# sage + generates 1 720P shot IN PARALLEL. Saves ~/.fanout-pods (id ip sport deploy_ts) for polling.
# No trap-on-exit (script exits after launching); a 35-min watchdog is the leak safety-net.
set -uo pipefail
K=$(cat ~/.runpod-key); PUB=$(cat ~/.ssh/id_rsa.pub)
IMG="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
N=${1:-4}
api(){ curl -s -m40 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }
PODS=(); declare -A IPP SPP

echo "=== deploy $N lean fan-out pods (no volume, 60GB disk) $(date +%T) ==="
for i in $(seq 1 $N); do
  ID=$(api -X POST https://rest.runpod.io/v1/pods -d "$(python3 -c "import json;print(json.dumps({'name':'fan$i','imageName':'$IMG','gpuTypeIds':['NVIDIA GeForce RTX 5090'],'gpuCount':1,'containerDiskInGb':60,'ports':['8188/http','22/tcp'],'computeType':'GPU','env':{'PUBLIC_KEY':'''$PUB'''}}))")" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
  [ -z "$ID" ] && { echo "  deploy #$i FAILED"; continue; }
  PODS+=("$ID"); echo "  #$i $ID"
done
[ ${#PODS[@]} -eq 0 ] && { echo "no pods"; exit 1; }
# watchdog backstop: terminate all after 35 min no matter what
nohup bash -c "sleep 2100; for p in ${PODS[*]}; do curl -s -X DELETE -H 'Authorization: Bearer $K' https://rest.runpod.io/v1/pods/\$p >/dev/null 2>&1; done" >/dev/null 2>&1 &
echo "WATCHDOG_ARMED (35min) for ${#PODS[@]} pods"

echo "=== wait SSH endpoints $(date +%T) ==="
for p in "${PODS[@]}"; do
  IP=-; SPORT=-
  for tt in $(seq 1 40); do
    read IP SPORT < <(api "https://rest.runpod.io/v1/pods/$p" | python3 -c "import sys,json;d=json.load(sys.stdin);pm=d.get('portMappings') or {};print(d.get('publicIp') or '-', pm.get('22') or '-')")
    [ "$IP" != - ] && [ "$SPORT" != - ] && break; sleep 8
  done
  IPP[$p]=$IP; SPP[$p]=$SPORT; echo "  $p -> $IP:$SPORT"
done

echo "=== SSH-launch lean boot on each (detached) $(date +%T) ==="
DEPLOY_TS=$(date +%s); idx=0
> ~/.fanout-pods
for p in "${PODS[@]}"; do
  idx=$((idx+1)); IP=${IPP[$p]}; SPORT=${SPP[$p]}
  echo "$p $IP $SPORT $DEPLOY_TS" >> ~/.fanout-pods
  [ "$IP" = - ] && { echo "  $p no ssh, skip"; continue; }
  SSH="ssh -i $HOME/.ssh/id_rsa -p $SPORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes root@$IP"
  for tt in $(seq 1 20); do $SSH 'echo ok' >/dev/null 2>&1 && break; sleep 6; done
  $SSH "git clone --depth 1 -q https://github.com/Simon99/h3-cloud-5090.git /workspace/h 2>/dev/null; setsid env GTAG=fan$idx GSEED=$((3000+idx)) bash /workspace/h/boot_fanout.sh >/workspace/boot.log 2>&1 </dev/null & echo LAUNCHED_$idx" 2>&1 | tail -1
done
echo "ALL_LAUNCHED ${#PODS[@]} pods  DEPLOY_TS=$DEPLOY_TS  $(date +%T)"
