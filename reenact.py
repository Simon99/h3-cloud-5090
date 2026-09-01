#!/usr/bin/env python3
"""REF2VA 重演:角色參考圖鎖身份 + ref_videos 餵動作參考影片 → 「這些角色做那支影片的動作」。
用法: reenact.py <podId> [--seed=N] [--out=name] [--refvid=路徑] [--w= --h=]
2026-09-01 首測:動作來源=人偶預演片(fight_v1),角色=旗袍女+熊貓。
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

PT = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
DEFAULT_VID = os.path.expanduser(
    "~/.claude/uploads/cf5c4cdc-a1be-492f-a8ef-db4a00fe2647/b0732613-fight_v1.mp4")
IMGS = [f"{PT}/char-qipao-fourview.png", f"{PT}/char-qipao-closeup.png",
        f"{PT}/char-panda-real-fourview.png", f"{PT}/char-panda-real-closeup.png",
        f"{PT}/scene-boxing-ring.png"]

PROMPT = (
    "Photorealistic live-action martial-arts film, cinematic, seamless VFX creature integration, "
    "night boxing arena with cool overhead spotlights and warm corner rim lights, hazy air. "
    "The woman shown in <Picture 1> and <Picture 2> — a young Chinese woman in a mini-length deep-red "
    "gold-embroidered silk qipao, bare-handed — and the panda shown in <Picture 3> and <Picture 4> — "
    "a towering realistic anthropomorphic giant panda in a white taekwondo dobok with a blue belt and "
    "red boxing gloves — spar inside the boxing ring shown in <Picture 5>. "
    "They perform EXACTLY the fight choreography shown in <Video 1>: the woman performs the red figure's "
    "movements, the panda performs the blue figure's movements, with the same timing, spacing and "
    "camera framing as the reference video. "
    "EXACTLY ONE woman and EXACTLY ONE panda, never duplicated. "
    "No mannequins, no checkerboard floor. No on-screen text, no logos, no speech.")


def main():
    pid = sys.argv[1]
    o = {"seed": "6001", "out": "reenact_a", "refvid": DEFAULT_VID, "w": "960", "h": "544"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    T.PROMPT = PROMPT   # build() 讀模組全域
    names = [T.upload(pid, f) for f in IMGS]
    vidname = T.upload(pid, os.path.expanduser(o["refvid"]))
    g = T.build(names, "match", int(o["seed"]), o["out"], w=int(o["w"]), h=int(o["h"]))
    # 掛動作參考影片:LoadVideo → GetVideoComponents → ref_videos dict
    g["rv"] = {"class_type": "LoadVideo", "inputs": {"file": vidname}}
    g["rvc"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["rv", 0]}}
    g["R2V"]["inputs"]["ref_videos"] = {"ref_video_0": ["rvc", 0]}
    g["R2V"]["inputs"]["prompt"] = PROMPT
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "re-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:700]); sys.exit(1)
    print(f"SUBMITTED job={job}", flush=True)
    t0 = time.time(); miss = 0
    while True:
        time.sleep(20)
        try: os.utime("/tmp/rp-lease-heartbeat", None)
        except Exception: pass
        try:
            h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60)); miss = 0
        except Exception as e:
            miss += 1; print(f"  poll err({miss}) {e}")
            if miss >= 6:
                try: json.load(T._get(T.base(pid) + "/queue", timeout=45)); miss = 0
                except Exception: print("COMFY_DEAD"); sys.exit(2)
            continue
        if job in h:
            st = h[job].get("status", {})
            if st.get("status_str") == "error":
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:900]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        el = time.time() - t0
        print(f"  running {el/60:.1f}min", flush=True)
        if el > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
