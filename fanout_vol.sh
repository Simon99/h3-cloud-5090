#!/usr/bin/env bash
# Volume-based fan-out speed test: deploy N pods ALL mounting the shared volume (EUR-IS-1),
# scp the lean vol-boot to each, run sage 720P gen IN PARALLEL reading models from the volume
# (no download). Saves ~/.fanout-pods (id ip sport deploy_ts). 30-min watchdog leak safety-net.
set -uo pipefail
K=$(cat ~/.runpod-key); PUB=$(cat ~/.ssh/id_rsa.pub)
IMG="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"; VOL=ufj8mzg8uq
N=${1:-3}
DIR=~/claude-sandboxes/director/cloud-5090
api(){ curl -s -m40 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }
PODS=(); declare -A IPP SPP

echo "=== deploy $N pods on shared volume $VOL (EUR-IS-1) $(date +%T) ==="
for i in $(seq 1 $N); do
  ID=$(api -X POST https://rest.runpod.io/v1/pods -d "$(python3 -c "import json;print(json.dumps({'name':'vf$i','imageName':'$IMG','gpuTypeIds':['NVIDIA GeForce RTX 5090'],'gpuCount':1,'networkVolumeId':'$VOL','containerDiskInGb':30,'dataCenterIds':['EUR-IS-1'],'ports':['8188/http','22/tcp'],'computeType':'GPU','env':{'PUBLIC_KEY':'''$PUB'''}}))")" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
  [ -z "$ID" ] && { echo "  #$i FAILED"; continue; }
  PODS+=("$ID"); echo "  #$i $ID"
done
[ ${#PODS[@]} -eq 0 ] && { echo "no pods"; exit 1; }
nohup bash -c "sleep 1800; for p in ${PODS[*]}; do curl -s -X DELETE -H 'Authorization: Bearer $K' https://rest.runpod.io/v1/pods/\$p >/dev/null 2>&1; done" >/dev/null 2>&1 &
echo "WATCHDOG_ARMED (30min)"

echo "=== wait SSH endpoints $(date +%T) ==="
for p in "${PODS[@]}"; do
  IP=-; SPORT=-
  for tt in $(seq 1 45); do
    read IP SPORT < <(api "https://rest.runpod.io/v1/pods/$p" | python3 -c "import sys,json;d=json.load(sys.stdin);pm=d.get('portMappings') or {};print(d.get('publicIp') or '-', pm.get('22') or '-')")
    [ "$IP" != - ] && [ "$SPORT" != - ] && break; sleep 8
  done
  IPP[$p]=$IP; SPP[$p]=$SPORT; echo "  $p -> $IP:$SPORT"
done

DEPLOY_TS=$(date +%s); idx=0; > ~/.fanout-pods
echo "=== scp vol-boot + launch on each $(date +%T) ==="
for p in "${PODS[@]}"; do
  idx=$((idx+1)); IP=${IPP[$p]}; SPORT=${SPP[$p]}
  echo "$p $IP $SPORT $DEPLOY_TS" >> ~/.fanout-pods
  [ "$IP" = - ] && { echo "  $p no ssh"; continue; }
  SSHO="-i $HOME/.ssh/id_rsa -p $SPORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"
  for tt in $(seq 1 20); do ssh -n $SSHO root@$IP 'echo ok' >/dev/null 2>&1 && break; sleep 6; done
  scp $SSHO "$DIR/boot_vol_fanout.sh" root@$IP:/root/boot_vol_fanout.sh >/dev/null 2>&1
  ssh -n $SSHO root@$IP "setsid env GTAG=vf$idx bash /root/boot_vol_fanout.sh >/root/boot.log 2>&1 </dev/null & echo LAUNCHED_$idx" 2>&1 | tail -1
done
echo "ALL_LAUNCHED ${#PODS[@]} pods DEPLOY_TS=$DEPLOY_TS $(date +%T)"
