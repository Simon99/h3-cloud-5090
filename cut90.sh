#!/bin/bash
set -e
SRC=/mnt/data2/wan22/out
T=/tmp/seg90; rm -rf $T; mkdir -p $T
F="-c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 192k -ar 44100 -ac 2"
seg(){ ffmpeg -v error -y -ss $3 -t $4 -i $SRC/up90_$2_00001_.mp4 -af "afade=t=in:d=0.12,afade=t=out:st=$(python3 -c "print(max(0,$4-0.25))"):d=0.25" $F $T/$1.mp4; }
slow(){ # slow <輸出> <來源名> <起> <長(來源秒數)> <倍率如0.4>
  DUR=$(python3 -c "print($4/$5)")
  ffmpeg -v error -y -ss $3 -t $4 -i $SRC/up90_$2_00001_.mp4 -f lavfi -t $DUR -i anullsrc=r=44100:cl=stereo \
    -filter_complex "[0:v]minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc,setpts=PTS/$5,fps=24[v]" \
    -map "[v]" -map 1:a -shortest $F $T/$1.mp4
}
### 第一幕 開場 ~19s
seg 01 o_arena 0.3 5.6
seg 02 cu_eyes 0.2 3.2
seg 03 cu_panda 0.2 3.2
seg 04 o_orbit 0.4 5.6
seg 05 cu_touch 0.3 3.4
### 交手一 ~16s
seg 06 w1_faceoff 0.6 5.2
seg 07 w2_kick 1.2 4.5
slow 07b w2_kick 4.0 1.3 0.4      # 命中瞬間 40% 慢放 → 3.25s
seg 08 w3_recoil 0.4 5.2
### 交手二 ~14s
seg 09 w4_sweep 0.6 4.8
seg 10 w5_flip 0.7 3.8
slow 10b w5_flip 2.6 1.2 0.5
seg 11 w6_counter 0.6 4.0
seg 12 w7_stagger 0.4 3.6
### 交手三 ~20s
seg 13 w8_haymaker 0.6 3.8
seg 14 w9_behind 0.7 3.0
seg 15 w10_throw 0.5 3.0
seg 16 w11_ropes 0.5 3.0
seg 17 w12_knee 0.6 4.2
slow 17b w12_knee 3.4 1.5 0.33    # 飛膝命中 33% 慢放 → 4.5s
### 收尾 ~11s
seg 18 w13_kneel 0.4 5.4
seg 19 w14_final 0.2 5.65
: > $T/list.txt
for s in 01 02 03 04 05 06 07 07b 08 09 10 10b 11 12 13 14 15 16 17 17b 18 19; do echo "file '$T/$s.mp4'" >> $T/list.txt; done
OUT=~/claude-sandboxes/director/research/experiments/panda-taekwondo/qipao_vs_panda_90s.mp4
ffmpeg -v error -y -f concat -safe 0 -i $T/list.txt -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 192k /tmp/pre90.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 /tmp/pre90.mp4)
ffmpeg -v error -y -i /tmp/pre90.mp4 \
  -vf "fade=t=in:st=0:d=0.8,fade=t=out:st=$(python3 -c "print(float('$D')-1.6)"):d=1.6" \
  -af "afade=t=in:d=0.8,afade=t=out:st=$(python3 -c "print(float('$D')-1.6)"):d=1.6" \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 192k $OUT
echo "=== 成片 ==="; ffprobe -v error -show_entries format=duration,size -of csv=p=0 $OUT
