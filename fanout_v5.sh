#!/usr/bin/env bash
# v5 fan-out: N Vast pods (picked by bandwidth/disk rules) × kyrox/h3-gen:v5 (Docker Hub)
# + HF_TOKEN parallel model download + film-mode shot ranges. Writes ~/.film5-pods.
# Per 瓶頸排程原則: poller pulls+destroys each pod as soon as ITS batch completes.
set -uo pipefail
K=$(cat ~/.vast-api-key); HFT=$(cat ~/.hf-token)
DIR=~/claude-sandboxes/director/cloud-5090
NTARGET=${NTARGET:-5}; NMIN=${NMIN:-3}; MANIFEST="${MANIFEST:-$DIR/bear_chains.json}"
VAST(){ ~/.local/bin/vastai "$@"; }

echo "=== 選最多 $NTARGET 台(頻寬≤0.005 + disk_bw≥4000 + <\$0.6)==="
OFFERS=$(VAST search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70' -o 'dph+' --raw 2>/dev/null | python3 -c "
import sys,json
o=json.load(sys.stdin)
ok=[x for x in o if x.get('dph_total',9)<0.6 and (x.get('inet_down_cost') or 0)<=0.005 and x.get('disk_bw',0)>=4000 and float(x.get('cuda_max_good') or 0)>=13.0]
ok.sort(key=lambda r:r.get('dph_total',9))
print(' '.join(str(x['id']) for x in ok[:$NTARGET+4]))")
echo "candidates: $OFFERS"
PODS=(); i=0
for OF in $OFFERS; do
  [ ${#PODS[@]} -ge $NTARGET ] && break
  R=$(VAST create instance "$OF" --image kyrox/h3-gen:v5 --disk 80 --ssh --direct --raw 2>&1)
  ID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('new_contract',''))" 2>/dev/null)
  [ -z "$ID" ] && { echo "  offer $OF 租失敗,跳過"; continue; }
  PODS+=("$ID"); echo "  pod#${#PODS[@]} = $ID (offer $OF)"
done
[ ${#PODS[@]} -lt $NMIN ] && { echo "只租到 ${#PODS[@]}/<$NMIN,中止並清理"; for p in "${PODS[@]}"; do echo y | VAST destroy instance "$p" >/dev/null 2>&1; done; exit 1; }
# 批次佇列:由大到小(使用者策略:最先就緒的 pod 通常網/碟最快 → 給最長鏈)
NP=${#PODS[@]}
mapfile -t BATCHQ < <(python3 -c "
import json
man=json.load(open('$MANIFEST'))
es=man['entries']; n=$NP
# greedy 裝箱:按幀數大→小放入目前最輕的箱
order=sorted(range(len(es)), key=lambda i:-es[i]['frames'])
bins=[[ ] for _ in range(n)]; load=[0]*n
for i in order:
    j=load.index(min(load)); bins[j].append(i); load[j]+=es[i]['frames']
bs=[(sorted(b), sum(es[i]['frames'] for i in b)) for b in bins if b]
bs.sort(key=lambda x:-x[1])   # 最重的箱排最前(給最先就緒 pod)
for b,_ in bs: print(','.join(map(str,b)))")
echo "實租 $NP 台,批次佇列(大→小): ${BATCHQ[*]}"
nohup bash -c "sleep 4500; for p in ${PODS[*]}; do echo y | $HOME/.local/bin/vastai destroy instance \$p >/dev/null 2>&1; done" >/dev/null 2>&1 &
echo "watchdog armed (75min)"

> ~/.film5-pods
SSHK="-i $HOME/.ssh/id_rsa -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"
declare -A LAUNCHED
QI=0
# 輪詢所有 pod,誰先 SSH 就緒誰領下一個(最大的)批次
for round in $(seq 1 90); do
  [ $QI -ge ${#BATCHQ[@]} ] && break
  for P in "${PODS[@]}"; do
    [ -n "${LAUNCHED[$P]:-}" ] && continue
    [ $QI -ge ${#BATCHQ[@]} ] && break
    read ST IP DP < <(VAST show instance "$P" --raw 2>/dev/null | python3 -c "
import sys,json;d=json.load(sys.stdin)
dp='-'
for k,v in (d.get('ports') or {}).items():
    if k.startswith('22/') and v: dp=v[0].get('HostPort','-')
print(d.get('actual_status'), d.get('public_ipaddr','-'), dp)" 2>/dev/null)
    if [ "$ST" = "running" ] && [ "$DP" != "-" ] && ssh -n $SSHK -p "$DP" root@"$IP" 'echo ok' >/dev/null 2>&1; then
      # 就緒 → CUDA 快篩 → 領批次
      if ! ssh -n $SSHK -p "$DP" root@"$IP" 'python -c "import torch;torch.cuda.init()"' >/dev/null 2>&1; then
        echo "  $P CUDA 快篩失敗,標記 dead"; LAUNCHED[$P]=DEAD; echo "$P - - - DEAD" >> ~/.film5-pods; continue
      fi
      GS=${BATCHQ[$QI]}; QI=$((QI+1))
      scp -P "$DP" $SSHK "$MANIFEST" "$DIR/cloud_gen.py" root@"$IP":/root/ >/dev/null 2>&1
      ssh -n $SSHK -p "$DP" root@"$IP" "cp /root/cloud_gen.py /workspace/h/cloud_gen.py" >/dev/null 2>&1
      ssh -n $SSHK -p "$DP" root@"$IP" "setsid env HF_TOKEN=$HFT MODEL_SET=fl2va GN=1 GSEED=2000 GUNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors GW=1312 GH=736 GF=141 GSTEPS=20 GSHOTS_FILE=/root/$(basename $MANIFEST) GSHOTS='$GS' bash /workspace/h/boot_v5.sh >/root/boot.log 2>&1 </dev/null & echo OK" >/dev/null 2>&1
      LAUNCHED[$P]=1
      echo "  第$QI個就緒: $P ← 批次[$GS]"
      echo "$P $IP $DP $GS" >> ~/.film5-pods
    fi
  done
  sleep 10
done
echo "ALL_LAUNCHED $(date +%T)"
cat ~/.film5-pods