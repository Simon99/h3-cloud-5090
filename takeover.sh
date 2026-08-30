#!/bin/bash
# 接管管理器:pod 47586617;驗證式收檔 B2/B3 → 補生 Y2 → 驗屍銷毀
set -u
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090; OUT=$DIR/cook_film
SSHK="-o StrictHostKeyChecking=no -o ConnectTimeout=8"
P=47586617; IP=76.121.3.151; DP=31288
log(){ echo "[$(date +%T)] TO $*"; }
ST(){ python3 $DIR/pod_stats.py log "$@" run_tag=cook0813b >/dev/null; }
vpull(){ # 驗證式收檔:遠端 size 穩定 → scp → ffprobe → 重試×4
  local c=$1
  for try in 1 2 3 4; do
    R=$(ssh -n $SSHK -p $DP root@$IP "ls /root/out/chain_${c}_*.mp4 2>/dev/null | head -1" 2>/dev/null)
    [ -z "$R" ] && return 1
    S1=$(ssh -n $SSHK -p $DP root@$IP "stat -c %s '$R'" 2>/dev/null); sleep 15
    S2=$(ssh -n $SSHK -p $DP root@$IP "stat -c %s '$R'" 2>/dev/null)
    [ -z "$S1" ] || [ "$S1" != "$S2" ] && { log "$c size 未穩定($S1→$S2), retry"; continue; }
    scp -q -P $DP $SSHK root@$IP:"$R" $OUT/chain_$c.mp4
    D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $OUT/chain_$c.mp4 2>/dev/null)
    [ -n "$D" ] && { log "GOT $c verified (${D}s, $S2 bytes)"; ST chain_done pod=$P chain=$c secs=750; return 0; }
    log "$c ffprobe 失敗, retry $try"; rm -f $OUT/chain_$c.mp4; sleep 20
  done
  return 1
}
finish(){ for try in 1 2 3; do
    echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1; sleep 5
    A=$(vastai show instances --api-key $K --raw 2>/dev/null | python3 -c "import sys,json;print(1 if any(d['id']==$P for d in json.load(sys.stdin)) else 0)" 2>/dev/null)
    [ "$A" = "0" ] && { log "destroyed+verified $P ($1)"; return; }
  done; log "WARN destroy 未確認"; }
T0=$(date +%s)
# Phase 1:等 B2、B3(驗證式)
for c in B2 B3; do
  for i in $(seq 1 50); do
    el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 55 ] && { finish deadline; exit 1; }
    vpull $c && break
    sleep 40
  done
done
# Phase 2:補生 Y2(idx 4,暖 pod)
log "dispatch Y2 regen"
ssh -n $SSHK -p $DP root@$IP "setsid env HF_TOKEN=$HFT MODEL_SET=fl2va GN=1 GSEED=2000 GUNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors GW=1312 GH=736 GF=141 GSTEPS=20 GSHOTS_FILE=/root/cook_chains.json GSHOTS='4' bash /workspace/h/boot_v5.sh >>/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
rm -f $OUT/chain_Y2.mp4
for i in $(seq 1 40); do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 55 ] && { finish deadline; exit 1; }
  vpull Y2 && break
  sleep 40
done
finish complete
n=$(ls $OUT/chain_*.mp4 2>/dev/null | wc -l)
log "TAKEOVER_DONE chains=$n/12"
