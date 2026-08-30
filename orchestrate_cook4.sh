#!/bin/bash
# 料理片收尾 orchestrator:單一權責(租/gate/派/收/殺全在此,無外部 watchdog)
# 剩餘 8 鏈:bins = 0,3,4 | 5,7,8 | 9,10;完工即殺 pod;唯一硬死線 DEADLINE_MIN
set -u
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090
OUT=$DIR/cook_film; mkdir -p $OUT
SSHK="-o StrictHostKeyChecking=no -o ConnectTimeout=8"
IDS=(N1 N2 N3 Y1 Y2 Y3 B1 B2 B3 S1 S2 S3)
declare -A THEME=([N]=noodle [Y]=nightmarket [B]=banquet [S]=sensory)
BINS=("0,3,4" "5,7,8")
ADOPT_POD=47578693; ADOPT_GS="9,10"
DEADLINE_MIN=75; T0=$(date +%s)
ST() { python3 $DIR/pod_stats.py log "$@" run_tag=cook0813b >/dev/null; }
log() { echo "[$(date +%T)] $*"; }

deadline_check() {
  el=$(( ($(date +%s)-T0)/60 ))
  if [ $el -ge $DEADLINE_MIN ]; then
    log "DEADLINE ${el}min → 清場"
    vastai show instances --api-key $K --raw 2>/dev/null | python3 -c "
import sys,json
for d in json.load(sys.stdin): print(d['id'])" | while read -r p; do
      echo y | vastai destroy instance $p --api-key $K >/dev/null 2>&1; log "destroyed $p (deadline)"
    done
    exit 1
  fi
}

# ---- Phase 1: 租 2 台(693 已在跑,認養)----
declare -A PIP PDP PGS PSTATE PLT
NPOD=0
PSTATE[$ADOPT_POD]=working; PGS[$ADOPT_POD]=$ADOPT_GS; PLT[$ADOPT_POD]=$(date +%s)
for AP in 47580302 47580306; do PSTATE[$AP]=new; PLT[$AP]=$(date +%s); done
NPOD=2
AINFO=$(vastai show instance $ADOPT_POD --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin); dp='-'
for kk,v in (d.get('ports') or {}).items():
    if kk.startswith('22/') and v: dp=v[0].get('HostPort','-')
print(d.get('public_ipaddr','-'), dp)")
PIP[$ADOPT_POD]=$(echo $AINFO|cut -d' ' -f1); PDP[$ADOPT_POD]=$(echo $AINFO|cut -d' ' -f2)
log "adopted $ADOPT_POD (${PIP[$ADOPT_POD]}:${PDP[$ADOPT_POD]}) batch[$ADOPT_GS]" 
vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70' -o 'dph+' --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
o=json.load(sys.stdin)
bl=set(open('/home/simon/claude-sandboxes/director/cloud-5090/host_blacklist.txt').read().split())
base=[x for x in o if str(x.get('machine_id')) not in bl and x.get('dph_total',9)<0.7 and (x.get('inet_down_cost') or 0)<=0.005 and float(x.get('cuda_max_good') or 0)>=13.0]
t1=[x for x in base if x.get('disk_bw',0)>=8000 and (x.get('inet_down') or 0)>=500]
t2=[x for x in base if x.get('disk_bw',0)>=4000]
pool=t1 if len(t1)>=3 else t2   # 嚴檔不足退寬檔,gate 兜底
pool.sort(key=lambda r:(r.get('dph_total',9)-min(r.get('disk_bw',0),20000)/1e6))
for x in pool[:8]: print(x['id'], x['dph_total'], x.get('disk_bw',0))" > /tmp/cook2-offers.txt
while read -r OF DPH DBW && [ $NPOD -lt 2 ]; do
  R=$(vastai create instance $OF --image kyrox/h3-gen:v5 --disk 80 --ssh --direct --raw --api-key $K 2>&1)
  ID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
  [ -z "$ID" ] && continue
  BADIP=$(vastai show instance $ID --raw --api-key $K 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('public_ipaddr',''))" )
  if [ "$BADIP" = "180.189.55.43" ]; then
    echo y | vastai destroy instance $ID --api-key $K >/dev/null 2>&1
    log "rejected $ID (黑名單IP)"; continue
  fi
  NPOD=$((NPOD+1)); PSTATE[$ID]=new; PLT[$ID]=$(date +%s)
  ST rented pod=$ID dph=$DPH disk_bw=$DBW
  log "rented pod#$NPOD = $ID (offer $OF dph=$DPH)"
done < /tmp/cook2-offers.txt
RETRY=0
while [ $NPOD -lt 2 ] && [ $RETRY -lt 3 ]; do
  RETRY=$((RETRY+1)); log "租到 $NPOD 台,8 分後重試($RETRY/4)"; sleep 480
  vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70' -o 'dph+' --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
o=json.load(sys.stdin)
bl=set(open('/home/simon/claude-sandboxes/director/cloud-5090/host_blacklist.txt').read().split())
base=[x for x in o if str(x.get('machine_id')) not in bl and x.get('dph_total',9)<0.7 and (x.get('inet_down_cost') or 0)<=0.005 and float(x.get('cuda_max_good') or 0)>=13.0]
t2=[x for x in base if x.get('disk_bw',0)>=4000]
t2.sort(key=lambda r:r.get('dph_total',9))
for x in t2[:8]: print(x['id'], x['dph_total'], x.get('disk_bw',0))" > /tmp/cook2-offers.txt
  while read -r OF DPH DBW && [ $NPOD -lt 2 ]; do
    R=$(vastai create instance $OF --image kyrox/h3-gen:v5 --disk 80 --ssh --direct --raw --api-key $K 2>&1)
    ID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
    [ -z "$ID" ] && continue
    NPOD=$((NPOD+1)); PSTATE[$ID]=new; PLT[$ID]=$(date +%s)
    ST rented pod=$ID dph=$DPH disk_bw=$DBW
    log "rented pod#$NPOD = $ID (offer $OF dph=$DPH)"
  done < /tmp/cook2-offers.txt
done
[ $NPOD -lt 2 ] && { log "重試耗盡仍租不到 2 台,中止"; exit 1; }

# ---- Phase 2+3: gate/派工/收檔/完工即殺 ----
QI=0
pulled() { ls $OUT/chain_$1.mp4 2>/dev/null | wc -l; }
assemble() {
  local t=$1; local f=$OUT/cook_${THEME[$t]}.mp4
  [ -f "$f" ] && return
  for c in ${t}1 ${t}2 ${t}3; do [ -f $OUT/chain_$c.mp4 ] || return; done
  for c in ${t}1 ${t}2 ${t}3; do echo "file '$OUT/chain_$c.mp4'"; done > $OUT/.cc_$t.txt
  ffmpeg -v error -y -f concat -safe 0 -i $OUT/.cc_$t.txt -an -c:v copy "$f" && log "ASSEMBLED ${THEME[$t]}"
}
while :; do
  deadline_check
  alldone=1
  for P in "${!PSTATE[@]}"; do
    S=${PSTATE[$P]}
    [ "$S" = "gone" ] && continue
    alldone=0
    INFO=$(vastai show instance $P --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json,time
try: d=json.load(sys.stdin)
except Exception: print('- - - 0'); sys.exit()
dp='-'
for kk,v in (d.get('ports') or {}).items():
    if kk.startswith('22/') and v: dp=v[0].get('HostPort','-')
age=(time.time()-d.get('start_date',time.time()))/60
print(d.get('actual_status','-'), d.get('public_ipaddr','-'), dp, f'{age:.1f}')")
    STT=$(echo $INFO|cut -d' ' -f1); IP=$(echo $INFO|cut -d' ' -f2); DP=$(echo $INFO|cut -d' ' -f3); AGE=$(echo $INFO|cut -d' ' -f4)
    case $S in
    new)
      if [ "$STT" != "running" ]; then
        if awk "BEGIN{exit !($AGE>9.0)}"; then
          echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
          ST gate_kill pod=$P reason=GateA_pull min=$AGE cost=0.09
          log "GateA KILL $P (${AGE}min)"; PSTATE[$P]=gone
        fi
        continue
      fi
      if ! ssh -n $SSHK -p $DP root@$IP 'echo ok' >/dev/null 2>&1; then
        if awk "BEGIN{exit !($AGE>14.0)}"; then
          echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
          ST gate_kill pod=$P reason=GateB2_ssh_zombie min=$AGE cost=0.08
          log "GateB2 KILL $P (running但ssh不通${AGE}min)"; PSTATE[$P]=gone
        fi
        continue
      fi
      if ! ssh -n $SSHK -p $DP root@$IP 'python -c "import torch;torch.cuda.init()"' >/dev/null 2>&1; then
        echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
        ST gate_kill pod=$P reason=GateB_cuda cost=0.09
        log "GateB KILL $P"; PSTATE[$P]=gone; continue
      fi
      ST running pod=$P min=$AGE
      [ $QI -ge ${#BINS[@]} ] && { PSTATE[$P]=idle; continue; }
      GS=${BINS[$QI]}; QI=$((QI+1))
      scp -q -P $DP $SSHK $DIR/cook_chains.json $DIR/cloud_gen.py root@$IP:/root/ </dev/null >/dev/null 2>&1
      ssh -n $SSHK -p $DP root@$IP "cp /root/cloud_gen.py /workspace/h/cloud_gen.py; setsid env HF_TOKEN=$HFT MODEL_SET=fl2va GN=1 GSEED=2000 GUNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors GW=1312 GH=736 GF=141 GSTEPS=20 GSHOTS_FILE=/root/cook_chains.json GSHOTS='$GS' bash /workspace/h/boot_v5.sh >/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
      PGS[$P]=$GS; PIP[$P]=$IP; PDP[$P]=$DP; PLT[$P]=$(date +%s); PSTATE[$P]=launched
      ST dispatch pod=$P batch=$GS
      log "DISPATCHED $P batch[$GS]"
      ;;
    launched|working)
      IP=${PIP[$P]}; DP=${PDP[$P]}
      el=$(( ($(date +%s)-PLT[$P])/60 ))
      # Gate C/E:4 分未下載夠且無 CHAIN_MODE 回執 → 殺+回佇列
      if [ "$S" = "launched" ] && [ $el -ge 5 ]; then
        GB=$(ssh -n $SSHK -p $DP root@$IP 'du -sBG /workspace/ComfyUI/models/diffusion_models 2>/dev/null | cut -f1 | tr -d G' </dev/null 2>/dev/null)
        CM=$(ssh -n $SSHK -p $DP root@$IP 'grep -c CHAIN_MODE /root/boot.log 2>/dev/null' </dev/null 2>/dev/null)
        if [ "${GB:-0}" -lt 3 ] && [ "${CM:-0}" -eq 0 ]; then
          echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
          ST gate_kill pod=$P reason=GateC_dl gb=${GB:-0} cost=0.12
          BINS+=("${PGS[$P]}"); log "GateC KILL $P dl=${GB:-0}GB → 批次回佇列"; PSTATE[$P]=gone; continue
        fi
        [ "${GB:-0}" -ge 3 ] && { ST dl_probe pod=$P rate=$(python3 -c "print(round(${GB:-0}/$el,1))"); PSTATE[$P]=working; }
      fi
      # 收檔
      for idx in ${PGS[$P]//,/ }; do
        c=${IDS[$idx]}
        [ -f $OUT/chain_$c.mp4 ] && continue
        R=$(ssh -n $SSHK -p $DP root@$IP "ls /root/out/chain_${c}_*.mp4 2>/dev/null | head -1" </dev/null 2>/dev/null)
        if [ -n "$R" ]; then
          scp -q -P $DP $SSHK root@$IP:"$R" $OUT/chain_$c.mp4 </dev/null && { log "GOT $c"; ST chain_done pod=$P chain=$c secs=750; assemble ${c:0:1}; }
        fi
      done
      # 完工即殺
      full=1
      for idx in ${PGS[$P]//,/ }; do [ -f $OUT/chain_${IDS[$idx]}.mp4 ] || full=0; done
      if [ $full -eq 1 ]; then
        echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
        hrs=$(python3 -c "print(round(($(date +%s)-${PLT[$P]})/3600+0.17,2))")
        ST destroyed pod=$P hours=$hrs
        log "COMPLETE→destroyed $P (batch ${PGS[$P]})"
        PSTATE[$P]=gone
      fi
      # 卡死偵測:30 分無新鏈落地
      if [ $el -ge 32 ] && [ "$S" = "working" ]; then
        got=0; for idx in ${PGS[$P]//,/ }; do [ -f $OUT/chain_${IDS[$idx]}.mp4 ] && got=$((got+1)); done
        if [ $got -eq 0 ]; then
          echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1 </dev/null
          ST gate_kill pod=$P reason=GateD_stall min=$el cost=0.25
          BINS+=("${PGS[$P]}"); log "GateD KILL $P (32min零產出) → 批次回佇列"; PSTATE[$P]=gone
        fi
      fi
      ;;
    idle) PSTATE[$P]=gone ;;
    esac
  done
  # 全部鏈到手?
  n=$(ls $OUT/chain_*.mp4 2>/dev/null | wc -l)
  if [ "$n" -ge 12 ]; then log "ALL_12_CHAINS"; break; fi
  [ $alldone -eq 1 ] && [ $QI -ge ${#BINS[@]} ] && { log "pods 盡但缺鏈:$n/12"; break; }
  sleep 35
done
for t in N Y B S; do assemble $t; done
ls $OUT/cook_*.mp4 2>/dev/null
log ORCH_END
