#!/usr/bin/env python3
"""Chain-manifest rescore: timeline comes from bear_chains.json (single source of truth).
Usage: rescore_chain.py <video.mp4> <out.mp4>
音床分段=manifest 每個 sub(shot,dur,cat);旁白=23 句 shot 對映 manifest 絕對時間,鏡頭開頭順流式。
"""
import json, os, subprocess, sys

DIR = os.path.dirname(os.path.abspath(__file__))
SCR = os.environ.get("SFX_NORM_DIR", os.path.expanduser(
    "/tmp/claude-1000/-home-simon-claude-sandboxes-director/cf5c4cdc-a1be-492f-a8ef-db4a00fe2647/scratchpad"))
NORM = f"{SCR}/sfxn"; NARRD = f"{SCR}/narr4"
VOICE = "zh-CN-YunjianNeural"; RATE = "-10%"
FADE_IN, FADE_OUT, BED_DB, NAR_VOL = 0.4, 0.8, -16, 1.5

LINES = [  # (shot#, text) — 同定稿 23 句
 (1,"清晨的中央山脈,住著一種只屬於台灣的熊。"),(2,"千年的原始森林,是牠們最後的家。"),
 (3,"蕨葉輕晃,有什麼正從林蔭深處走來。"),(4,"台灣黑熊——這座島嶼唯一的原生熊。"),
 (5,"烏黑的毛、圓短的耳,山林裡最神祕的臉。"),(6,"胸前的白色V,是牠獨一無二的印記。"),
 (7,"別看牠是熊,其實多半吃素。"),(8,"嫩葉、果實、菇類,都是牠的食物。"),
 (9,"強壯的爪,能抓住最粗糙的樹皮。"),(10,"樹冠高處,牠折枝築巢,休息也瞭望。"),
 (11,"遇到溪流毫不猶豫,牠也是游泳好手。"),(12,"清澈的山澗,是牠安靜的飲水處。"),
 (13,"繁殖季後,母熊獨自育幼,兩年寸步不離。"),(14,"玩耍,是幼熊獨立前的功課。"),
 (15,"中央山脈綿延三百公里,曾經都是牠們的家。"),(16,"雲海翻湧,這片風景已存在百萬年。"),
 (17,"牠獨來獨往,活動範圍可達一百平方公里。"),(18,"但這片森林,正被道路與開發切成碎片。"),
 (19,"全台灣,只剩下不到六百隻。"),(20,"每一隻,都無比珍貴。"),
 (21,"紅外線相機下,有一群人正守護著牠們。"),(22,"牠走回迷霧深處——願這片山林,永遠有熊。"),
 (23,"天亮了,新的一天屬於山,也屬於熊。"),
]

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print("ERR:", " ".join(cmd)[:180], "\n", r.stderr[-500:]); sys.exit(1)
def dur(p):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                                 "-of","csv=p=0",p],capture_output=True,text=True).stdout.strip())

def main(video, out):
    man = json.load(open(f"{DIR}/bear_chains.json", encoding="utf-8"))
    FPS = man["fps"]; TOTAL = man["total_seconds"]
    # manifest → 每 shot 絕對起點/時長/音床類別(唯一時間軸真相)
    shot_start = {}; segs = []; t = 0.0
    for e in man["entries"]:
        for sub in e["subs"]:
            shot_start[sub["shot"]] = t
            segs.append((t, sub["dur"], sub["cat"]))
            t += sub["dur"]
    assert abs(t - TOTAL) < 0.05, f"timeline mismatch {t} vs {TOTAL}"

    # TTS(牠→它替換,冪等)
    tts = os.path.expanduser("~/.local/bin/edge-tts")
    os.makedirs(NARRD, exist_ok=True)
    for i,(s,txt) in enumerate(LINES):
        p = f"{NARRD}/l{i:02d}.mp3"
        if not os.path.exists(p):
            run([tts,"--voice",VOICE,f"--rate={RATE}","--text",txt.replace("牠","它"),"--write-media",p])

    # 旁白順流擺位(鏡頭開頭起)
    offs=[]; prev=0.0
    for i,(s,txt) in enumerate(LINES):
        d = dur(f"{NARRD}/l{i:02d}.mp3")
        st = max(shot_start[s] + 0.3, prev + 0.35)
        offs.append((st,d)); prev = st + d
    print(f"narration coverage: {sum(d for _,d in offs)/TOTAL*100:.0f}%  last_end={prev:.1f}/{TOTAL}")
    assert prev <= TOTAL - 0.3, "旁白溢出片尾,需精簡"

    inputs=[]; fc=[]; labels=[]
    for i,(st,d) in enumerate(offs):
        ms=int(st*1000)
        inputs += ["-i", f"{NARRD}/l{i:02d}.mp3"]
        fc.append(f"[{i}:a]adelay={ms}|{ms},volume={NAR_VOL}[n{i}]"); labels.append(f"[n{i}]")
    fc.append("".join(labels)+f"amix=inputs={len(labels)}:normalize=0:duration=longest,apad=whole_dur={TOTAL},atrim=end={TOTAL},aresample=32000[nar]")
    nar=f"{SCR}/narrC_all.wav"
    run(["ffmpeg","-v","error","-y",*inputs,"-filter_complex",";".join(fc),"-map","[nar]","-ar","32000","-ac","2",nar])

    # 音床:manifest segs 逐段鋪 + 底床
    cdur={c:dur(f"{NORM}/{c}.wav") for c in set(c for _,_,c in segs)}
    inputs=[]; fc=[]; labels=[]; occ={}
    for k,(st,dsec,c) in enumerate(segs):
        occ[c]=occ.get(c,0)+1
        seglen=dsec+FADE_OUT; d=cdur[c]
        loop = d<=seglen+0.2
        off = 0.0 if loop else ((occ[c]-1)*13.7)%(d-seglen-0.1)
        idx=len(inputs)//2; inputs+=["-i",f"{NORM}/{c}.wav"]
        ch=[]
        if loop: ch.append("aloop=loop=-1:size=2147483647")
        ch+=[f"atrim=start={off:.2f}:end={off+seglen:.2f}","asetpts=PTS-STARTPTS",
             f"afade=t=in:st=0:d={FADE_IN}",f"afade=t=out:st={seglen-FADE_OUT:.2f}:d={FADE_OUT}"]
        ms=int(st*1000); ch.append(f"adelay={ms}|{ms}")
        fc.append(f"[{idx}:a]"+",".join(ch)+f"[s{k}]"); labels.append(f"[s{k}]")
    bidx=len(inputs)//2; inputs+=["-i",f"{NORM}/quiet_forest.wav"]
    fc.append(f"[{bidx}:a]aloop=loop=-1:size=2147483647,atrim=end={TOTAL},asetpts=PTS-STARTPTS,volume={BED_DB}dB,afade=t=in:st=0:d=1,afade=t=out:st={TOTAL-2:.2f}:d=2[bed]")
    labels.append("[bed]")
    fc.append("".join(labels)+f"amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=end={TOTAL},loudnorm=I=-27:TP=-3:LRA=11,aresample=32000[amb]")
    amb=f"{SCR}/ambC_all.wav"
    run(["ffmpeg","-v","error","-y",*inputs,"-filter_complex",";".join(fc),"-map","[amb]","-ar","32000","-ac","2",amb])

    run(["ffmpeg","-v","error","-y","-i",video,"-i",amb,"-i",nar,
         "-filter_complex","[2:a]asplit=2[sc][nmix];[1:a][sc]sidechaincompress=threshold=0.015:ratio=6:attack=80:release=600:makeup=1[duck];[duck][nmix]amix=inputs=2:normalize=0:duration=first[aout]",
         "-map","0:v","-map","[aout]","-c:v","copy","-c:a","aac","-ar","32000","-b:a","192k",
         "-movflags","+faststart",out])
    print("DONE:", out, f"{dur(out):.2f}s")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
