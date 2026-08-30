#!/bin/bash
# 料理四小品:輪詢各 pod 拉 chain_*.mp4,每題湊齊即組裝(靜音版)
# pods 檔格式: <pod> <ip> <port> <批次indices>
DIR=~/claude-sandboxes/director/cloud-5090
OUT=$DIR/cook_film; mkdir -p $OUT
SSHK="-i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o ConnectTimeout=8"
IDS=(N1 N2 N3 Y1 Y2 Y3 B1 B2 B3 S1 S2 S3)
declare -A THEME=([N]=noodle [Y]=nightmarket [B]=banquet [S]=sensory)

assemble() { # $1=字母
  local t=$1 f=$OUT/cook_${THEME[$t]}.mp4
  [ -f "$f" ] && return
  for c in ${t}1 ${t}2 ${t}3; do [ -f $OUT/chain_$c.mp4 ] || return; done
  for c in ${t}1 ${t}2 ${t}3; do echo "file '$OUT/chain_$c.mp4'"; done > $OUT/.cc_$t.txt
  ffmpeg -v error -y -f concat -safe 0 -i $OUT/.cc_$t.txt -an -c:v copy "$f" && \
    echo "ASSEMBLED ${THEME[$t]} $(date +%T)"
}

for round in $(seq 1 90); do
  while read -r P IP DP GS; do
    [ "$GS" = "DEAD" ] && continue
    for idx in ${GS//,/ }; do
      c=${IDS[$idx]}
      [ -f $OUT/chain_$c.mp4 ] && continue
      # v5 ComfyUI --output-directory /root/out
      R=$(ssh -n $SSHK -p $DP root@$IP "ls /root/out/chain_${c}_*.mp4 2>/dev/null | head -1")
      if [ -n "$R" ]; then
        scp -q -P $DP $SSHK root@$IP:"$R" $OUT/chain_$c.mp4 && echo "GOT $c ($(date +%T))"
        assemble ${c:0:1}
      fi
    done
  done < ~/.film5-pods
  n=$(ls $OUT/chain_*.mp4 2>/dev/null | wc -l)
  [ "$n" -ge 12 ] && { echo ALL_CHAINS_DONE; break; }
  sleep 45
done
ls -la $OUT/cook_*.mp4 2>/dev/null
