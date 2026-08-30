#!/bin/bash
# 收尾管理器:雙租先到先得,全程埋點(util+step),驗證式收檔,批次 [4,7,8]=Y2,B2,B3
set -u
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090; OUT=$DIR/cook_film
SSHK="-o StrictHostKeyChecking=no -o ConnectTimeout=8"
GS="4,7,8"; CHAINS="Y2 B2 B3"
log(){ echo "[$(date +%T)] FB $*"; }
ST(){ python3 $DIR/pod_stats.py log "$@" run_tag=cook0813b >/dev/null; }
vkill(){ for t in 1 2 3; do echo y | vastai destroy instance $1 --api-key $K >/dev/null 2>&1; sleep 5
  A=$(vastai show instances --api-key $K --raw 2>/dev/null | python3 -c "import sys,json;print(1 if any(d['id']==$1 for d in json.load(sys.stdin)) else 0)" 2>/dev/null)
  [ "$A" = "0" ] && { log "destroyed+verified $1 ($2)"; return; }; done; log "WARN $1 destroy未確認"; }
info(){ vastai show instance $1 --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print('- - -'); sys.exit()
dp='-'
for kk,v in (d.get('ports') or {}).items():
    if kk.startswith('22/') and v: dp=v[0].get('HostPort','-')
print(d.get('actual_status','-'), d.get('public_ipaddr','-'), dp)"; }
vpull(){ local c=$1
  R=$(ssh -n $SSHK -p $DP root@$IP "ls /root/out/chain_${c}_*.mp4 2>/dev/null | head -1" 2>/dev/null)
  [ -z "$R" ] && return 1
  S1=$(ssh -n $SSHK -p $DP root@$IP "stat -c %s '$R'" 2>/dev/null); sleep 12
  S2=$(ssh -n $SSHK -p $DP root@$IP "stat -c %s '$R'" 2>/dev/null)
  { [ -z "$S1" ] || [ "$S1" != "$S2" ]; } && return 1
  scp -q -P $DP $SSHK root@$IP:"$R" $OUT/chain_$c.mp4 2>/dev/null
  D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $OUT/chain_$c.mp4 2>/dev/null)
  [ -n "$D" ] && { log "GOT $c verified(${D}s)"; ST chain_done pod=$P chain=$c secs=750; return 0; }
  rm -f $OUT/chain_$c.mp4; return 1; }

# Phase1: 雙租
PODS=()
vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70' -o 'dph+' --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
bl=set(open('/home/simon/claude-sandboxes/director/cloud-5090/host_blacklist.txt').read().split())
o=json.load(sys.stdin)
ok=[x for x in o if str(x.get('machine_id')) not in bl and x.get('dph_total',9)<1.0 and (x.get('inet_down_cost') or 0)<=0.005 and x.get('disk_bw',0)>=4000 and float(x.get('cuda_max_good') or 0)>=13.0]
ok.sort(key=lambda r:(-(r.get('reliability2') or 0), r.get('dph_total',9)))
seen=set(); out=[]
for x in ok:
    m=x.get('machine_id')
    if m in seen: continue
    seen.add(m); out.append(x)
for x in out[:2]: print(x['id'])" | while read -r OF; do
  R=$(vastai create instance $OF --image kyrox/h3-gen:v5 --disk 80 --ssh --direct --raw --api-key $K 2>&1)
  ID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
  [ -n "$ID" ] && echo "$ID" >> /tmp/fb-pods.txt
done
mapfile -t PODS < /tmp/fb-pods.txt; rm -f /tmp/fb-pods.txt
log "rented: ${PODS[*]:-none}"
[ ${#PODS[@]} -eq 0 ] && { log ABORT_no_pods; exit 1; }
for p in "${PODS[@]}"; do ST rented pod=$p; done
T0=$(date +%s); P=""; IP=""; DP=""
# Phase2: 先到先得
while [ -z "$P" ]; do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 16 ] && { for p in "${PODS[@]}"; do vkill $p rent_timeout; done; log ABORT_gate; exit 1; }
  for p in "${PODS[@]}"; do
    read -r STT PIP PDP <<< $(info $p)
    [ "$STT" != "running" ] && continue
    ssh -n $SSHK -p $PDP root@$PIP 'echo ok' >/dev/null 2>&1 || continue
    ssh -n $SSHK -p $PDP root@$PIP 'python -c "import torch;torch.cuda.init()"' >/dev/null 2>&1 || { vkill $p cuda; PODS=($(printf '%s\n' "${PODS[@]}" | grep -v "^$p$")); continue; }
    P=$p; IP=$PIP; DP=$PDP; break
  done
  sleep 25
done
log "winner $P ($IP:$DP)"
for p in "${PODS[@]}"; do [ "$p" != "$P" ] && vkill $p loser_release; done
# Phase3: 派工 + 埋點監控
scp -q -P $DP $SSHK $DIR/cook_chains.json $DIR/cloud_gen.py root@$IP:/root/ >/dev/null 2>&1
ssh -n $SSHK -p $DP root@$IP "cp /root/cloud_gen.py /workspace/h/cloud_gen.py; setsid env HF_TOKEN=$HFT MODEL_SET=fl2va GN=1 GSEED=2000 GUNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors GW=1312 GH=736 GF=141 GSTEPS=20 GSHOTS_FILE=/root/cook_chains.json GSHOTS='$GS' bash /workspace/h/boot_v5.sh >/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
ST dispatch pod=$P batch=$GS; log "DISPATCHED $P [$GS]"
LT=$(date +%s); LSTEP=""; IDLE=0; GOTN=0
while :; do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 85 ] && { vkill $P deadline; log FB_TIMEOUT; exit 1; }
  del=$(( ($(date +%s)-LT)/60 ))
  # 埋點:util + step(下載期 util 低是正常,>12 分後才啟用停滯判定)
  PROBE=$(ssh -n $SSHK -p $DP root@$IP 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1; tail -c 300 /root/comfy.log 2>/dev/null | tr "\r" "\n" | grep -oE "[0-9]+/20" | tail -1' 2>/dev/null | tr '\n' ' ')
  UTIL=$(echo $PROBE | cut -d' ' -f1); STP=$(echo $PROBE | cut -d' ' -f2)
  if [ $del -ge 12 ]; then
    if [ -n "$UTIL" ] && [ "$UTIL" -lt 20 ] 2>/dev/null && [ "$STP" = "$LSTEP" ]; then
      IDLE=$((IDLE+1))
      if [ $IDLE -ge 4 ]; then vkill $P "stall(util=$UTIL,step=$STP)"; log FB_STALL; exit 1; fi
    elif [ -z "$UTIL" ]; then
      IDLE=$((IDLE+1))   # 探測失敗也累計(哨兵v2的洞,修正)
      [ $IDLE -ge 6 ] && { vkill $P probe_dead; log FB_PROBE_DEAD; exit 1; }
    else IDLE=0; fi
  fi
  LSTEP=$STP
  for c in $CHAINS; do
    [ -f $OUT/chain_$c.mp4 ] && continue
    vpull $c && GOTN=$((GOTN+1))
  done
  n=0; for c in $CHAINS; do [ -f $OUT/chain_$c.mp4 ] && n=$((n+1)); done
  [ $n -eq 3 ] && { vkill $P complete; log FB_DONE; exit 0; }
  sleep 40
done
