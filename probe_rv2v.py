#!/usr/bin/env python3
"""Director rv2v 探測:源影片(人偶預演)+ 參考圖(旗袍女/熊貓/擂台)→ 換人保編排。
用法: probe_rv2v.py <podId> [--seed=N] [--out=name] [--steps=25]
timeline_data 模板取自 AIMixer/ComfyUI_MiniMaxH3_Director 官方 rv2v 範例(2026-09-01)。
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

PT = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
VID = os.path.expanduser("~/.claude/uploads/cf5c4cdc-a1be-492f-a8ef-db4a00fe2647/b0732613-fight_v1.mp4")
IMGS = [f"{PT}/char-qipao-fourview.png", f"{PT}/char-qipao-closeup.png",
        f"{PT}/char-panda-real-fourview.png", f"{PT}/char-panda-real-closeup.png",
        f"{PT}/scene-boxing-ring.png"]
W, H, FR = 960, 544, 158          # 源片 170 幀 → 對齊 17k+5 = 158
PROMPT = (
    "Replace the red mannequin figure in <Video 1> with the woman from <Picture 1> and <Picture 2> — "
    "a young Chinese woman in a mini-length deep-red gold-embroidered silk qipao, bare-handed. "
    "Replace the blue mannequin figure in <Video 1> with the panda from <Picture 3> and <Picture 4> — "
    "a towering realistic anthropomorphic giant panda in a white taekwondo dobok with a blue belt and "
    "red boxing gloves. Set the fight inside the boxing ring shown in <Picture 5>. "
    "Keep the exact choreography, timing, spacing and camera motion of <Video 1>. "
    "Photorealistic live-action martial-arts film, cinematic lighting. "
    "EXACTLY ONE woman and EXACTLY ONE panda. No mannequins, no checkerboard floor, no text, no logos.")


def timeline(vidname):
    return json.dumps({
        "version": 4, "editMode": "global", "timelineMode": "video",
        "totalFrames": FR, "frameRate": 24.0, "width": W, "height": H, "refMaxSize": 864,
        "output": {"mode": "fixed", "longEdge": 864, "width": W, "height": H,
                   "maxExportFrames": 0, "exportMode": "all",
                   "continuityEnabled": False, "continuityOverlapFrames": 9},
        "videoClips": [],
        "video": {"fileName": vidname, "videoFile": vidname, "subfolder": "", "type": "input",
                  "frames": [], "frameMap": []},
        "global": {"taskType": "rv2v — 参考素材改视频(Reference Video Edit)",
                   "prompt": PROMPT,
                   "refs": [{"index": i, "imageFile": os.path.basename(p)} for i, p in enumerate(IMGS)],
                   "referenceVideo": {}, "continuousReference": False,
                   "genImage": {"imageFile": ""}},
        "segments": [{"id": "s0", "start": 0, "length": FR, "frameCount": FR,
                      "durationSec": round(FR / 24.0, 2), "prompt": "", "taskType": "",
                      "refs": [], "referenceVideo": {}, "genImage": {"imageFile": ""},
                      "negativePrompt": ""}],
        "gen": {"defaultFrameCount": FR},
        "runSelectEnabled": False, "runSelection": [],
    }, ensure_ascii=False)


def main():
    pid = sys.argv[1]
    o = {"seed": "7001", "out": "rv2v_a", "steps": "25"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    names = [T.upload(pid, f) for f in IMGS]
    vidname = T.upload(pid, VID)
    # timeline 的 imageFile 要用上傳後的實際檔名
    tl = timeline(vidname)
    for orig, actual in zip([os.path.basename(p) for p in IMGS], names):
        tl = tl.replace(f'"imageFile": "{orig}"', f'"imageFile": "{actual}"')
    g = {
        "L_model": {"class_type": "UNETLoader",
                    "inputs": {"unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
                               "weight_dtype": "default"}},
        "L_clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": T.CLIP, "type": "minimax"}},
        "L_vvae": {"class_type": "VAELoader", "inputs": {"vae_name": T.VVAE}},
        "L_avae": {"class_type": "VAELoader", "inputs": {"vae_name": T.AVAE}},
        "dir": {"class_type": "MiniMaxH3Director", "inputs": {
            "model": ["L_model", 0], "video_vae": ["L_vvae", 0], "audio_vae": ["L_avae", 0],
            "clip": ["L_clip", 0],
            "task_type": "rv2v — 参考素材改视频(Reference Video Edit)",
            "global_prompt": PROMPT,
            "bd_grp_sample": "采样设置", "bd_grp_advanced": "高级采样 Advanced", "bd_grp_perf": "性能 Performance",
            "cfg": 1.0, "seed": int(o["seed"]), "frame_rate": 24.0,
            "width": W, "height": H, "ref_max_size": 864, "total_frames": FR,
            "timeline_data": tl,
            "steps": int(o["steps"]), "sampler": "res_multistep", "scheduler": "simple",
            "shift_video": 12.0, "shift_audio": 3.0,
            "clear_vram_between_segments": True, "export_source_images": False,
        }},
        "mk": {"class_type": "CreateVideo",
               "inputs": {"images": ["dir", 0], "audio": ["dir", 1], "fps": 24.0}},
        "sv": {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": o["out"], "format": "mp4", "codec": "h264"}},
    }
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "rv-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:1200]); sys.exit(1)
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
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:1500]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        el = time.time() - t0
        print(f"  running {el/60:.1f}min", flush=True)
        if el > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
