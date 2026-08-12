#!/usr/bin/env python3
"""Build the chain manifest (bear_chains.json) from bear_shots.txt.
鏈=同場景連續動作(原生 storyboard 一次生成);硬切處維持單鏡。
Manifest 是影(生成)音(rescore 時間軸)共用的單一真相。
幀數必須落在 17k+5 網格:雙鏡鏈=294f(12.25s,每子鏡 6.125s)、單鏡=141f(5.875s)。
"""
import json, re, os

FPS = 24.0
DIR = os.path.dirname(os.path.abspath(__file__))
txt = open(f"{DIR}/bear_shots.txt", encoding="utf-8").read()
prompts = [b.strip() for b in re.split(r'\n-{3,}\n', txt) if b.strip()]
assert len(prompts) == 23

# 場景群(1-indexed shot 編號):雙鏡鏈 10 條 + 單鏡 3
CHAINS = [
    ("A", [1, 2]),    # 晨曦航拍 → 樹冠滑行(連續下降)
    ("B", [3, 4]),    # 蕨類林床騷動 → 熊步出林蔭(連續揭示)
    ("C", [5, 6]),    # 臉特寫 → 胸斑特寫(連續推近)
    ("D", [7, 8]),    # 覓食 → 進食特寫
    ("E", [9, 10]),   # 攀樹 → 樹冠遠眺
    ("F", [11, 12]),  # 涉水 → 溪邊飲水
    ("G", [13, 14]),  # 母熊幼崽 → 幼崽玩耍
    ("H", [15, 16]),  # 森林航拍 → 雲海
    ("I", [17]),      # 林徑獨行(情緒轉場,單鏡)
    ("J", [18, 19]),  # 伐林邊界 → 空寂森林
    ("K", [20]),      # 警覺的眼(單鏡)
    ("L", [21]),      # 紅外夜視(視覺風格獨立,單鏡)
    ("M", [22, 23]),  # 走入迷霧 → 晨光結尾
]
# 音床類別(沿用 rescore 的 shot→cat 映射)
CAT = {1:"mountain_wind",2:"canopy_wind",3:"forest_birds",4:"forest_birds",5:"quiet_forest",
 6:"quiet_forest",7:"quiet_forest",8:"quiet_forest",9:"quiet_forest",10:"canopy_wind",
 11:"stream",12:"stream",13:"forest_birds",14:"forest_birds",15:"mountain_wind",
 16:"mountain_wind",17:"forest_birds",18:"somber_wind",19:"somber_wind",20:"quiet_forest",
 21:"night_insects",22:"quiet_forest",23:"mountain_wind"}

def strip_tail(p):
    """去掉各鏡 prompt 裡的 Audio 段(鏈級只留一段 audio)與收尾句,取主描述。"""
    main = p.split("\n\nAudio:")[0].strip()
    return main

entries = []
for cid, shots in CHAINS:
    if len(shots) == 1:
        s = shots[0]
        entries.append({"id": cid, "frames": 141, "shots": shots,
                        "subs": [{"shot": s, "dur": 141/FPS, "cat": CAT[s]}],
                        "prompt": prompts[s-1]})
    else:
        a, b = shots
        sub = 294/2/FPS  # 6.125s
        pa, pb = strip_tail(prompts[a-1]), strip_tail(prompts[b-1])
        # 鏈級 audio 描述:合併兩鏡的 Audio 行
        aud = []
        for s in shots:
            m = re.search(r'Audio:\s*(.+)', prompts[s-1])
            if m: aud.append(m.group(1).strip().rstrip('.'))
        prompt = (f"Photorealistic wildlife documentary, National Geographic quality. "
                  f"A continuous sequence in one take, two connected shots.\n\n"
                  f"Storyboard:\n[0s-{sub:.2f}s] {pa}\n[{sub:.2f}s-{2*sub:.2f}s] {pb}\n\n"
                  f"Audio: {'; then '.join(aud)}. No voices, no speech, no music.\n"
                  f"No people, no on-screen text, no subtitles, no captions.")
        entries.append({"id": cid, "frames": 294, "shots": shots,
                        "subs": [{"shot": a, "dur": sub, "cat": CAT[a]},
                                 {"shot": b, "dur": sub, "cat": CAT[b]}],
                        "prompt": prompt})

total_f = sum(e["frames"] for e in entries)
man = {"fps": FPS, "grid": "17k+5", "total_frames": total_f,
       "total_seconds": round(total_f/FPS, 3), "entries": entries}
out = f"{DIR}/bear_chains.json"
json.dump(man, open(out, "w"), ensure_ascii=False, indent=1)
print(f"manifest: {len(entries)} entries ({sum(1 for e in entries if len(e['shots'])==2)} chains + "
      f"{sum(1 for e in entries if len(e['shots'])==1)} singles), "
      f"{total_f}f = {total_f/FPS:.1f}s (原 23×141={23*141}f={23*141/24:.1f}s)")
for e in entries:
    print(f"  {e['id']}: shots{e['shots']} {e['frames']}f")
