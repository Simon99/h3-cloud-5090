#!/bin/bash
# 租約制看門狗:有進展就自動續租,停滯才殺——不用固定死線
#
# 兩階段:
#   Phase 1 開機期:進度 = 狀態推進 / CPU / GPU / 記憶體活動 / HTTP 上線
#                  連續 STALL_POLLS 次無進展 → 殺
#   Phase 2 就緒期:ComfyUI 已上線,租約由「操作者心跳檔」持有
#                  我每做一件事就 touch 心跳;超過 IDLE_MIN 沒人碰 → 殺
#                  (等於:我停止工作,pod 也跟著死,不會忘記關)
# 最外層還有 HARD_CAP_MIN 成本保險(不是判斷依據,只是天花板)
set -u
PID=${1:?podId}
D=~/claude-sandboxes/director/cloud-5090
HB=/tmp/rp-lease-heartbeat
POLL=45; STALL_POLLS=8; IDLE_MIN=15; HARD_CAP_MIN=180; UNK_MAX=40
K=$(cat ~/.runpod-key)
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0"
T0=$(date +%s); touch $HB
log(){ echo "[$(date +%T)] LEASE $*"; }

metrics(){ curl -sS -m 20 -X POST https://api.runpod.io/graphql -H "Content-Type: application/json" \
  -H "User-Agent: $UA" -H "Authorization: Bearer $K" \
  -d "{\"query\":\"query { pod(input: {podId: \\\"$PID\\\"}) { desiredStatus runtime { uptimeInSeconds gpus { gpuUtilPercent memoryUtilPercent } container { cpuPercent memoryPercent } } } }\"}" 2>/dev/null \
 | python3 -c "
import sys,json
try: p=json.load(sys.stdin)['data']['pod'] or {}
except Exception: print('ERR 0 0 0 0'); raise SystemExit
rt=p.get('runtime') or {}
g=(rt.get('gpus') or [{}])[0]; c=rt.get('container') or {}
print(p.get('desiredStatus','?'), rt.get('uptimeInSeconds',0),
      g.get('gpuUtilPercent',0), g.get('memoryUtilPercent',0), c.get('cpuPercent',0))" ; }

postmortem(){
  local T=/tmp/rp-postmortem-$PID
  mkdir -p $T
  for f in "" progress.txt boot.log comfy.log; do
    curl -s -m 12 "https://${PID}-8189.proxy.runpod.net/$f" -o "$T/${f:-index.html}" 2>/dev/null
  done
  log "取證存於 $T:"
  for f in index.html progress.txt boot.log comfy.log; do
    [ -s "$T/$f" ] && log "  $f ($(stat -c %s $T/$f)b) 末尾: $(tail -c 300 "$T/$f" | tr '\n' ' ' | tail -c 200)"
  done
}
kill_pod(){ log "TERMINATING ($1) — 先取證"; postmortem; python3 $D/runpod.py kill $PID; exit ${2:-1}; }

PHASE=boot; STALL=0; UNK=0; LAST=""
while :; do
  EL=$(( ($(date +%s)-T0)/60 ))
  [ $EL -ge $HARD_CAP_MIN ] && kill_pod "hard_cap_${EL}min"
  read -r ST UP GU GM CPU <<< "$(metrics)"
  curl -s -o /tmp/rp_obj.json -m 15 "https://${PID}-8188.proxy.runpod.net/object_info" 2>/dev/null
  # 驗內容不驗狀態碼:proxy 服務未就緒時也回 200 + 佔位 HTML(2026-08-22 學費)
  HTTP=$(python3 -c "
import json,sys
try:
    d=json.load(open('/tmp/rp_obj.json'))
    print('200' if isinstance(d,dict) and len(d)>50 else 'html')
except Exception: print('html')" 2>/dev/null)

  if [ "$PHASE" = "boot" ] && [ "$HTTP" = "200" ]; then
    PHASE=ready; touch $HB
    log "COMFY_UP after ${EL}min → 進入就緒期(租約改由心跳檔持有,閒置 ${IDLE_MIN} 分即殺)"
    echo "$PID" > /tmp/rp-ready.txt
  fi

  if [ "$PHASE" = "boot" ]; then
    # 主信號:pod 內每 20 秒寫的 /root/progress.txt(時間戳 已下載bytes comfy.log大小)
    # 經 8189 靜態服務暴露。拿不到 = unknown(容器還沒起/映像還在拉),**不算停滯**
    PROG=$(curl -s -m 12 "https://${PID}-8189.proxy.runpod.net/progress.txt" 2>/dev/null | tr -d '\r\n')
    PROG=$(echo "$PROG" | grep -oE '^[0-9]+ [0-9]* [0-9]*' || true)
    if [ -z "$PROG" ]; then
      UNK=$((UNK+1))
      log "unknown ${EL}min (${UNK}/${UNK_MAX}) st=$ST — 進度端點尚未上線,不視為停滯"
      [ $UNK -ge $UNK_MAX ] && kill_pod "no_signal_${EL}min"
    else
      if [ "$UNK" != "0" ]; then
        log "進度端點上線,抓一次 boot.log 供早期診斷"
        curl -s -m 12 "https://${PID}-8189.proxy.runpod.net/boot.log" -o /tmp/rp-boot-early.log 2>/dev/null
        [ -s /tmp/rp-boot-early.log ] && log "  boot.log 末尾: $(tail -c 200 /tmp/rp-boot-early.log | tr '\n' ' ')"
      fi
      UNK=0
      BYTES=$(echo "$PROG" | awk '{print $2}')
      if [ "$BYTES" != "$LAST" ]; then
        STALL=0; GB=$(python3 -c "print(f\"{int('${BYTES:-0}' or 0)/1e9:.1f}\")" 2>/dev/null)
        log "進展 ${EL}min 已下載 ${GB}GB gpu=${GU}% → 續租"
      else
        STALL=$((STALL+1)); log "停滯 ${EL}min (${STALL}/${STALL_POLLS}) bytes 未增加"
        [ $STALL -ge $STALL_POLLS ] && kill_pod "boot_stall_${EL}min"
      fi
      LAST="$BYTES"
    fi
  else
    IDLE=$(( ($(date +%s) - $(stat -c %Y $HB)) / 60 ))
    if [ $IDLE -ge $IDLE_MIN ]; then kill_pod "operator_idle_${IDLE}min"; fi
    [ $((EL % 5)) -eq 0 ] && log "就緒中 ${EL}min 操作者閒置 ${IDLE}/${IDLE_MIN} 分 gpu=${GU}%"
  fi
  sleep $POLL
done
