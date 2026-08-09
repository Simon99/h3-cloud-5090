#!/usr/bin/env bash
# FILM RUN: 5 pods share the volume (EUR-IS-1), split the 23 shots (5/5/5/4/4), each generates
# its shots warm (sage 720P), models read from the volume (no download). Writes ~/.film-pods
# (id ip sport gshots). 40-min watchdog leak safety-net. Poll+pull+assemble happen separately.
set -uo pipefail
K=$(cat ~/.runpod-key); PUB=$(cat ~/.ssh/id_rsa.pub)
IMG="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"; VOL=ufj8mzg8uq
DIR=~/claude-sandboxes/director/cloud-5090
ASSIGN=("0,1,2,3,4" "5,6,7,8,9" "10,11,12,13,14" "15,16,17,18" "19,20,21,22")
api(){ curl -s -m40 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }
PODS=(); declare -A IPP SPP

echo "=== deploy 5 pods on shared volume $VOL (EUR-IS-1) $(date +%T) ==="
for i in 1 2 3 4 5; do
  ID=$(api -X POST https://rest.runpod.io/v1/pods -d "$(python3 -c "import json;print(json.dumps({'name':'film$i','imageName':'$IMG','gpuTypeIds':['NVIDIA GeForce RTX 5090'],'gpuCount':1,'networkVolumeId':'$VOL','containerDiskInGb':30,'dataCenterIds':['EUR-IS-1'],'ports':['8188/http','22/tcp'],'computeType':'GPU','env':{'PUBLIC_KEY':'''$PUB'''}}))")" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
  [ -z "$ID" ] && { echo "  #$i FAILED"; continue; }
  PODS+=("$ID"); echo "  #$i $ID  shots=${ASSIGN[$((i-1))]}"
done
[ ${#PODS[@]} -eq 0 ] && { echo "no pods"; exit 1; }
nohup bash -c "sleep 2400; for p in ${PODS[*]}; do curl -s -X DELETE -H 'Authorization: Bearer $K' https://rest.runpod.io/v1/pods/\$p >/dev/null 2>&1; done" >/dev/null 2>&1 &
echo "WATCHDOG_ARMED (40min)"

echo "=== wait SSH endpoints $(date +%T) ==="
for p in "${PODS[@]}"; do
  IP=-; SPORT=-
  for tt in $(seq 1 45); do
    read IP SPORT < <(api "https://rest.runpod.io/v1/pods/$p" | python3 -c "import sys,json;d=json.load(sys.stdin);pm=d.get('portMappings') or {};print(d.get('publicIp') or '-', pm.get('22') or '-')")
    [ "$IP" != - ] && [ "$SPORT" != - ] && break; sleep 8
  done
  IPP[$p]=$IP; SPP[$p]=$SPORT; echo "  $p -> $IP:$SPORT"
done

> ~/.film-pods; idx=0
echo "=== scp {boot,cloud_gen,shots} + launch per-pod shot ranges $(date +%T) ==="
for p in "${PODS[@]}"; do
  idx=$((idx+1)); IP=${IPP[$p]}; SPORT=${SPP[$p]}; GS=${ASSIGN[$((idx-1))]}
  echo "$p $IP $SPORT $GS" >> ~/.film-pods
  [ "$IP" = - ] && { echo "  $p no ssh"; continue; }
  SSHO="-i $HOME/.ssh/id_rsa -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"
  for tt in $(seq 1 20); do ssh -n $SSHO -p $SPORT root@$IP 'echo ok' >/dev/null 2>&1 && break; sleep 6; done
  scp -P $SPORT $SSHO "$DIR/boot_vol_fanout.sh" "$DIR/cloud_gen.py" "$DIR/bear_shots.txt" root@$IP:/root/ >/dev/null 2>&1
  ssh -n $SSHO -p $SPORT root@$IP "setsid env GSHOTS='$GS' bash /root/boot_vol_fanout.sh >/root/boot.log 2>&1 </dev/null & echo LAUNCHED_$idx shots=$GS" 2>&1 | tail -1
done
echo "ALL_LAUNCHED ${#PODS[@]} pods $(date +%T)"
