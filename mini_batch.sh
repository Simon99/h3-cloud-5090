#!/bin/bash
# 迷你管理器 v2:單 pod 單批次 [5,7,8]=Y3,B2,B3;拒收重試;驗屍式 destroy
set -u
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090; OUT=$DIR/cook_film
SSHK="-o StrictHostKeyChecking=no -o ConnectTimeout=8"
GS="5,7,8"; CHAINS="Y3 B2 B3"
log(){ echo "[$(date +%T)] MB $*"; }
ST(){ python3 $DIR/pod_stats.py log "$@" run_tag=cook0813b >/dev/null; }
P=""
for RTRY in 1 2 3 4 5 6; do
  OF=$(vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70' -o 'dph+' --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
bl=set(open('/home/simon/claude-sandboxes/director/cloud-5090/host_blacklist.txt').read().split())
o=json.load(sys.stdin)
ok=[x for x in o if str(x.get('machine_id')) not in bl and x.get('dph_total',9)<1.0 and (x.get('inet_down_cost') or 0)<=0.005 and x.get('disk_bw',0)>=4000 and float(x.get('cuda_max_good') or 0)>=13.0]
ok.sort(key=lambda r:(-(r.get('reliability2') or 0), r.get('dph_total',9)))
print(ok[0]['id'] if ok else '')")
  [ -z "$OF" ] && { log "無合格 offer(round $RTRY)"; sleep 90; continue; }
  R=$(vastai create instance $OF --image kyrox/h3-gen:v5 --disk 80 --ssh --direct --raw --api-key $K 2>&1)
  CAND=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
  [ -z "$CAND" ] && { log "租失敗(round $RTRY)"; sleep 45; continue; }
  IPC=$(vastai show instance $CAND --raw --api-key $K 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('public_ipaddr',''))" 2>/dev/null)
  if [ "$IPC" = "180.189.55.43" ]; then
    MID=$(vastai show instance $CAND --raw --api-key $K 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('machine_id',''))" 2>/dev/null)
    echo y | vastai destroy instance $CAND --api-key $K >/dev/null 2>&1
    [ -n "$MID" ] && echo "$MID" >> $DIR/host_blacklist.txt
    log "黑名單IP拒收(round $RTRY),machine $MID 入黑名單,換 offer"; continue
  fi
  P=$CAND; break
done
[ -z "$P" ] && { log "重試耗盡,放棄"; exit 1; }
ST rented pod=$P; log "rented $P"
T0=$(date +%s); DEADLINE=70
finish(){
  for try in 1 2 3; do
    echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1; sleep 5
    A=$(vastai show instances --api-key $K --raw 2>/dev/null | python3 -c "import sys,json;print(1 if any(d['id']==$P for d in json.load(sys.stdin)) else 0)" 2>/dev/null)
    [ "$A" = "0" ] && { log "destroyed+verified $P ($1)"; return; }
    log "destroy 未生效,重試 $try"
  done
  log "WARN destroy 三次未確認,$P 可能殭屍,需人工"
}
trap 'finish trap' EXIT
DISPATCHED=0; IP=""; DP=""
while :; do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge $DEADLINE ] && { finish deadline; trap - EXIT; exit 1; }
  INFO=$(vastai show instance $P --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json,time
try: d=json.load(sys.stdin)
except Exception: print('- - -'); sys.exit()
dp='-'
for kk,v in (d.get('ports') or {}).items():
    if kk.startswith('22/') and v: dp=v[0].get('HostPort','-')
print(d.get('actual_status','-'), d.get('public_ipaddr','-'), dp)")
  STT=$(echo $INFO|cut -d' ' -f1); IP=$(echo $INFO|cut -d' ' -f2); DP=$(echo $INFO|cut -d' ' -f3)
  if [ $DISPATCHED -eq 0 ]; then
    [ "$STT" != "running" ] && { [ $el -ge 13 ] && { ST gate_kill pod=$P reason=GateA cost=0.06; finish gateA; trap - EXIT; exit 1; }; sleep 30; continue; }
    ssh -n $SSHK -p $DP root@$IP 'echo ok' >/dev/null 2>&1 || { [ $el -ge 18 ] && { ST gate_kill pod=$P reason=GateB2_ssh cost=0.09; finish ssh_zombie; trap - EXIT; exit 1; }; sleep 30; continue; }
    ssh -n $SSHK -p $DP root@$IP 'python -c "import torch;torch.cuda.init()"' >/dev/null 2>&1 || { ST gate_kill pod=$P reason=GateB_cuda cost=0.06; finish cuda; trap - EXIT; exit 1; }
    scp -q -P $DP $SSHK $DIR/cook_chains.json $DIR/cloud_gen.py root@$IP:/root/ >/dev/null 2>&1
    ssh -n $SSHK -p $DP root@$IP "cp /root/cloud_gen.py /workspace/h/cloud_gen.py; setsid env HF_TOKEN=$HFT MODEL_SET=fl2va GN=1 GSEED=2000 GUNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors GW=1312 GH=736 GF=141 GSTEPS=20 GSHOTS_FILE=/root/cook_chains.json GSHOTS='$GS' bash /workspace/h/boot_v5.sh >/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
    DISPATCHED=1; LT=$(date +%s); ST dispatch pod=$P batch=$GS; log "DISPATCHED $P [$GS]"
    sleep 35; continue
  fi
  # 進度速率:模型下載探針(5分時);之後收檔
  del=$(( ($(date +%s)-LT)/60 ))
  if [ $del -ge 5 ] && [ $del -lt 7 ]; then
    GB=$(ssh -n $SSHK -p $DP root@$IP 'du -sBG /workspace/ComfyUI/models/diffusion_models 2>/dev/null | cut -f1 | tr -d G' 2>/dev/null)
    if [ "${GB:-0}" -lt 3 ] && ! ssh -n $SSHK -p $DP root@$IP 'grep -q CHAIN_MODE /root/boot.log' 2>/dev/null; then
      ST gate_kill pod=$P reason=GateC_dl cost=0.09; finish gateC; trap - EXIT; exit 1
    fi
  fi
  full=1
  for c in $CHAINS; do
    [ -f $OUT/chain_$c.mp4 ] && continue
    R=$(ssh -n $SSHK -p $DP root@$IP "ls /root/out/chain_${c}_*.mp4 2>/dev/null | head -1" 2>/dev/null)
    if [ -n "$R" ]; then scp -q -P $DP $SSHK root@$IP:"$R" $OUT/chain_$c.mp4 && { log "GOT $c"; ST chain_done pod=$P chain=$c secs=750; }; fi
    [ -f $OUT/chain_$c.mp4 ] || full=0
  done
  [ $full -eq 1 ] && { hrs=$(python3 -c "print(round(($(date +%s)-T0)/3600,2))"); ST destroyed pod=$P hours=$hrs; finish complete; trap - EXIT; log MB_DONE; exit 0; }
  sleep 35
done
