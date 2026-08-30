#!/bin/bash
# REF2VA 金絲雀:租 1 台、下 ref2va 模型、不生成,只把 ComfyUI 起來供查 schema
# 全程 gate + 驗屍 destroy;pod 資訊寫 /tmp/ref2va-pod.txt 供後續互動用
set -u
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090
SSHK="-o StrictHostKeyChecking=no -o ConnectTimeout=8"
log(){ echo "[$(date +%T)] CANARY $*"; }
ST(){ python3 $DIR/pod_stats.py log "$@" run_tag=ref2va >/dev/null 2>&1; }

P=""
for RTRY in 1 2 3 4 5; do
  OF=$(vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>120' -o 'dph+' --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
bl=set(open('$DIR/host_blacklist.txt').read().split())
o=json.load(sys.stdin)
ok=[x for x in o if str(x.get('machine_id')) not in bl and x.get('dph_total',9)<0.75 and (x.get('inet_down_cost') or 0)<=0.005 and x.get('disk_bw',0)>=4000 and float(x.get('cuda_max_good') or 0)>=13.0]
ok.sort(key=lambda r:(-(r.get('reliability2') or 0), r.get('dph_total',9)))
print(ok[0]['id'] if ok else '')")
  [ -z "$OF" ] && { log "無合格 offer(round $RTRY)"; sleep 60; continue; }
  R=$(vastai create instance $OF --image kyrox/h3-gen:v5 --disk 130 --ssh --direct --raw --api-key $K 2>&1)
  CAND=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
  [ -z "$CAND" ] && { log "租失敗(round $RTRY)"; sleep 45; continue; }
  IPC=$(vastai show instance $CAND --raw --api-key $K 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('public_ipaddr',''))" 2>/dev/null)
  if [ "$IPC" = "180.189.55.43" ] || [ "$IPC" = "38.117.87.56" ]; then
    MID=$(vastai show instance $CAND --raw --api-key $K 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('machine_id',''))" 2>/dev/null)
    echo y | vastai destroy instance $CAND --api-key $K >/dev/null 2>&1
    [ -n "$MID" ] && echo "$MID" >> $DIR/host_blacklist.txt
    log "黑名單IP拒收,換 offer"; continue
  fi
  P=$CAND; break
done
[ -z "$P" ] && { log "租不到,放棄"; exit 1; }
ST rented pod=$P; log "rented $P"
T0=$(date +%s)
finish(){ for t in 1 2 3; do echo y | vastai destroy instance $P --api-key $K >/dev/null 2>&1; sleep 5
  A=$(vastai show instances --api-key $K --raw 2>/dev/null | python3 -c "import sys,json;print(1 if any(d['id']==$P for d in json.load(sys.stdin)) else 0)" 2>/dev/null)
  [ "$A" = "0" ] && { log "destroyed+verified ($1)"; return; }; done; log "WARN destroy 未確認"; }

IP=""; DP=""
while :; do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 20 ] && { finish gate_timeout; exit 1; }
  INFO=$(vastai show instance $P --raw --api-key $K 2>/dev/null | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print('- - -'); sys.exit()
dp='-'
for kk,v in (d.get('ports') or {}).items():
    if kk.startswith('22/') and v: dp=v[0].get('HostPort','-')
print(d.get('actual_status','-'), d.get('public_ipaddr','-'), dp)")
  STT=$(echo $INFO|cut -d' ' -f1); IP=$(echo $INFO|cut -d' ' -f2); DP=$(echo $INFO|cut -d' ' -f3)
  [ "$STT" != "running" ] && { [ $el -ge 13 ] && { ST gate_kill pod=$P reason=GateA; finish gateA; exit 1; }; sleep 30; continue; }
  ssh -n $SSHK -p $DP root@$IP 'echo ok' >/dev/null 2>&1 || { [ $el -ge 18 ] && { ST gate_kill pod=$P reason=GateB2; finish ssh_zombie; exit 1; }; sleep 30; continue; }
  ssh -n $SSHK -p $DP root@$IP 'python -c "import torch;torch.cuda.init()"' >/dev/null 2>&1 || { ST gate_kill pod=$P reason=GateB_cuda; finish cuda; exit 1; }
  break
done
log "ready $P ($IP:$DP)"
echo "$P $IP $DP" > /tmp/ref2va-pod.txt
# 下 ref2va 模型 + 起 ComfyUI(GN=0 不生成)
scp -q -P $DP $SSHK $DIR/cloud_gen.py root@$IP:/root/ >/dev/null 2>&1
ssh -n $SSHK -p $DP root@$IP "cp /root/cloud_gen.py /workspace/h/cloud_gen.py; setsid env HF_TOKEN=$HFT MODEL_SET=ref2va GN=0 bash /workspace/h/boot_v5.sh >/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
log "boot dispatched (MODEL_SET=ref2va, GN=0)"
# 等 ComfyUI 起來(V5_READY 或 API 有回應)
for i in $(seq 1 90); do
  el=$(( ($(date +%s)-T0)/60 )); [ $el -ge 55 ] && { finish deadline; exit 1; }
  R=$(ssh -n $SSHK -p $DP root@$IP 'curl -s -m 5 http://127.0.0.1:8188/object_info 2>/dev/null | head -c 20' 2>/dev/null)
  if [ -n "$R" ]; then log "ComfyUI API 上線 (${el}min)"; break; fi
  GB=$(ssh -n $SSHK -p $DP root@$IP 'du -sBG /workspace/ComfyUI/models/diffusion_models 2>/dev/null | cut -f1 | tr -d G' 2>/dev/null)
  [ $((i % 6)) -eq 0 ] && log "waiting... ${el}min dl=${GB:-0}GB"
  sleep 20
done
log CANARY_READY
