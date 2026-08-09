#!/usr/bin/env bash
# Phase 1 (short, run foreground w/ timeout 600s): deploy 5090 + volume, launch boot.sh DETACHED on the pod,
# arm a watchdog that auto-terminates in 40 min (leak safety), save state to ~/.runpod-current.
# Then poll boot.log with short calls; finish_pod.sh collects + terminates on done.
set -uo pipefail
K=$(cat ~/.runpod-key); PUB=$(cat ~/.ssh/id_rsa.pub)
VOL=ufj8mzg8uq; IMG="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
api(){ curl -s -m40 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }

POD=$(api -X POST https://rest.runpod.io/v1/pods -d "$(python3 -c "import json;print(json.dumps({'name':'bear-test','imageName':'$IMG','gpuTypeIds':['NVIDIA GeForce RTX 5090'],'gpuCount':1,'networkVolumeId':'$VOL','containerDiskInGb':40,'ports':['8188/http','22/tcp'],'dataCenterIds':['EUR-IS-1'],'computeType':'GPU','env':{'PUBLIC_KEY':'''$PUB'''}}))")" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
[ -z "$POD" ] && { echo "DEPLOY_FAILED"; exit 1; }
echo "pod=$POD"
IP=-; SPORT=-
for i in $(seq 1 40); do
  read IP SPORT < <(api "https://rest.runpod.io/v1/pods/$POD" | python3 -c "import sys,json;d=json.load(sys.stdin);pm=d.get('portMappings') or {};print(d.get('publicIp') or '-', pm.get('22') or '-')")
  [ "$IP" != - ] && [ "$SPORT" != - ] && break; sleep 10
done
[ "$IP" = - ] && { echo "NO_SSH_ENDPOINT"; exit 1; }
SSH="ssh -i $HOME/.ssh/id_rsa -p $SPORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes root@$IP"
echo "waiting sshd @ $IP:$SPORT"
for i in $(seq 1 30); do $SSH 'echo ok' >/dev/null 2>&1 && { echo "sshd up"; break; }; sleep 6; done
$SSH 'cd /workspace/h && git pull -q; setsid env INSTALL_SAGE=1 INSTALL_SPECTRUM=1 GSPECTRUM=1 GTAG=full GW=1312 GH=736 GF=141 GSTEPS=20 GN=1 bash /workspace/h/boot.sh >/workspace/boot.log 2>&1 </dev/null & echo LAUNCHED' 2>&1 | tail -1
echo "$POD $IP $SPORT" > ~/.runpod-current
# watchdog: plain nohup (survives), auto-terminate in 40 min as a leak safety-net
nohup bash -c "sleep 3600; curl -s -X DELETE -H 'Authorization: Bearer $K' 'https://rest.runpod.io/v1/pods/$POD' >/dev/null 2>&1" >/dev/null 2>&1 &
echo "WATCHDOG_ARMED pid=$! (auto-terminate $POD in 60min)"
echo "READY $POD $IP:$SPORT"
