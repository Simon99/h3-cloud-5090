#!/bin/bash
# 修正後的標準跑批流程(2026-08-29 事故後版本)
#   ① 續租活到「產出已驗證落地」為止,不以「環境就緒」為終止條件
#   ② 每一鏡完成即刻下載 + ffprobe 驗證,不等整批
#   ③ 全部落地後才 release(release 本身會終止並驗屍)
# 用法: run_batch.sh <podId> <outdir> <batchfile>
#   batchfile 每行:<輸出名> <turbo_ab.py 的參數...>
set -u
PID=${1:?podId}; OUT=${2:?outdir}; BATCH=${3:?batchfile}
DIR=~/claude-sandboxes/director/cloud-5090
W=~/claude-sandboxes/memory-system/scripts/runpod_warden.py
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0"
mkdir -p "$OUT"
log(){ echo "[$(date +%T)] $*"; }
renew(){ python3 $W lease $PID --ttl-min 45 --max-life-min 240 --owner director --purpose "batch run" >/dev/null 2>&1; }

# 背景續租心跳:每 5 分一次,活到本腳本結束(trap 收尾)
( while :; do renew; sleep 300; done ) & HB=$!

# 收尾:腳本一結束(正常/中斷/當掉皆然)就把租約改成短引信,
#   讓「忘了 release」的最大損失從 45 分縮到 EXIT_TTL 分。
#   RELEASE_WHEN_DONE=1 則直接銷毀(不打算接下一批時用)。
# 背景:08-29 11:14 兩顆 pod 因續租迴圈提早退出、租約到期被 warden 擊殺,
#   損失四支已完成影片——當時只修了「心跳要活到產出落地」,沒修「退出後的引信長度」。
finish(){
  kill $HB 2>/dev/null
  if [ "${RELEASE_WHEN_DONE:-0}" = "1" ]; then
    python3 $W release $PID >/dev/null 2>&1 && echo "[$(date +%T)] 已 release $PID"
  else
    python3 $W lease $PID --ttl-min ${EXIT_TTL:-10} --max-life-min 240 \
      --owner director --purpose "batch run" >/dev/null 2>&1 \
      && echo "[$(date +%T)] 租約改短引信 ${EXIT_TTL:-10} 分(未 release,可接下一批)"
  fi
}
trap finish EXIT

# 等 ComfyUI 就緒(驗內容不驗狀態碼)
for i in $(seq 1 80); do
  # 先清殘檔:curl 失敗時沿用上一顆 pod 的舊檔會誤判 COMFY_UP(2026-09-04 空燒 502 事故)
  rm -f /tmp/oi_rb.json
  curl -sf -m 15 "https://${PID}-8188.proxy.runpod.net/object_info" -o /tmp/oi_rb.json 2>/dev/null
  python3 -c "
import json,sys
try: sys.exit(0 if len(json.load(open('/tmp/oi_rb.json')))>50 else 1)
except Exception: sys.exit(1)" && { log "COMFY_UP"; UP=1; break; }
  sleep 30
done
# 等不到就是失敗,不准掉進批次空燒(2026-09-04 兩度 502 空燒事故)
[ "${UP:-0}" = "1" ] || { log "COMFY_NEVER_UP,整批中止"; exit 3; }

FAIL=0
while read -r NAME ARGS; do
  [ -z "$NAME" ] && continue
  log "▶ $NAME  ($ARGS)"
  python3 $DIR/${RUNNER:-turbo_ab.py} $PID $ARGS --out=$NAME 2>&1 | tail -2
  RC=${PIPESTATUS[0]}
  # exit 2 = 跑手判定 ComfyUI 已死(映像無 sshd 無法重啟)→ 整批中止,別讓後續每鏡再撞一次
  if [ "$RC" = "2" ]; then log "✗ ComfyUI 已死,整批中止(剩餘鏡次未執行)"; FAIL=2; break; fi
  # ② 立刻下載並驗證,不等整批
  ok=0
  for t in 1 2 3; do
    curl -s -A "$UA" -m 240 "https://${PID}-8188.proxy.runpod.net/view?filename=${NAME}_00001_.mp4&type=output" -o "$OUT/$NAME.mp4"
    D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/$NAME.mp4" 2>/dev/null)
    if [ -n "$D" ]; then log "  ✓ 落地 $NAME.mp4 ${D}s $(stat -c %s "$OUT/$NAME.mp4")b"; ok=1; break; fi
    log "  下載/驗證失敗,重試 $t"; sleep 10
  done
  [ $ok -eq 0 ] && { log "  ✗ $NAME 取回失敗"; FAIL=1; }
  renew
done < "$BATCH"

log "全部處理完畢 FAIL=$FAIL — 產出已落地,現在才可釋放 pod"
echo BATCH_DONE
