#!/usr/bin/env python3
"""rv2v 單角色填充:木偶預演片 + 旗袍女參考 → 完整版動作片。
用法: probe_rv2v1.py <podId> --src=<預演mp4> [--frames=90] [--seed=N] [--out=name]"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

PT = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
IMGS = [f"{PT}/char-qipao-fourview.png", f"{PT}/char-qipao-closeup.png", f"{PT}/scene-boxing-ring.png"]
W, H = 960, 544
PROMPT = ("Replace the red wooden mannequin figure in <Video 1> with the woman from <Picture 1> and "
          "<Picture 2> — a young Chinese woman in a mini-length deep-red gold-embroidered silk qipao, "
          "bare-handed, embroidered flat shoes. Set the action inside the boxing ring shown in "
          "<Picture 3>, cool white overhead spotlights, warm corner rim lights, hazy air. "
          "Keep the EXACT choreography, timing, spacing and camera motion of <Video 1>. "
          "Photorealistic live-action martial-arts film. EXACTLY ONE woman. "
          "No mannequins, no grey void. No on-screen text, no logos, no speech.")


def timeline(vidname, fr):
    return json.dumps({
        "version": 4, "editMode": "global", "timelineMode": "video",
        "totalFrames": fr, "frameRate": 30.0, "width": W, "height": H, "refMaxSize": 864,
        "output": {"mode": "fixed", "longEdge": 864, "width": W, "height": H,
                   "maxExportFrames": 0, "exportMode": "all",
                   "continuityEnabled": False, "continuityOverlapFrames": 9},
        "videoClips": [],
        "video": {"fileName": vidname, "videoFile": vidname, "subfolder": "", "type": "input",
                  "frames": [], "frameMap": []},
        "global": {"taskType": "rv2v — 参考素材改视频(Reference Video Edit)",
                   "prompt": PROMPT,
                   "refs": [{"index": i, "imageFile": os.path.basename(p)} for i, p in enumerate(IMGS)],
                   "referenceVideo": {}, "continuousReference": False, "genImage": {"imageFile": ""}},
        "segments": [{"id": "s0", "start": 0, "length": fr, "frameCount": fr,
                      "durationSec": round(fr / 30.0, 2), "prompt": "", "taskType": "",
                      "refs": [], "referenceVideo": {}, "genImage": {"imageFile": ""},
                      "negativePrompt": ""}],
        "gen": {"defaultFrameCount": fr},
        "runSelectEnabled": False, "runSelection": [],
    }, ensure_ascii=False)


def main():
    pid = sys.argv[1]
    o = {"src": "", "frames": "90", "seed": "8801", "out": "rv2v1"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    fr = int(o["frames"])
    names = [T.upload(pid, f) for f in IMGS]
    vidname = T.upload(pid, os.path.expanduser(o["src"]))
    tl = timeline(vidname, fr)
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
            "cfg": 1.0, "seed": int(o["seed"]), "frame_rate": 30.0,
            "width": W, "height": H, "ref_max_size": 864, "total_frames": fr,
            "timeline_data": tl,
            "steps": 25, "sampler": "res_multistep", "scheduler": "simple",
            "shift_video": 12.0, "shift_audio": 3.0,
            "clear_vram_between_segments": True, "export_source_images": False,
        }},
        "mk": {"class_type": "CreateVideo", "inputs": {"images": ["dir", 0], "audio": ["dir", 1], "fps": 30.0}},
        "sv": {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": o["out"], "format": "mp4", "codec": "h264"}},
    }
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "rf-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job: print("SUBMIT_ERR", json.dumps(r)[:900]); sys.exit(1)
    print("SUBMITTED", flush=True); t0 = time.time(); miss = 0
    while True:
        time.sleep(20)
        try: os.utime("/tmp/rp-lease-heartbeat", None)
        except Exception: pass
        try:
            h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60)); miss = 0
        except Exception as e:
            miss += 1
            if miss >= 6:
                try: json.load(T._get(T.base(pid) + "/queue", timeout=45)); miss = 0
                except Exception: print("COMFY_DEAD"); sys.exit(2)
            continue
        if job in h:
            st = h[job].get("status", {})
            if st.get("status_str") == "error":
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:900]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        print(f"  running {(time.time()-t0)/60:.1f}min", flush=True)
        if time.time() - t0 > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
