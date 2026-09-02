#!/usr/bin/env python3
"""LTX-2.5 雲端實驗跑手(兩段式蒸餾,接線取自 Lightricks 官方範例子圖)。
模式:
  --mode=t2v   文生(速度/音訊 canary)
  --mode=flf2v 首尾幀(--first --last 關鍵幀檔名,LTXVAddGuide 釘 0 與末幀)
  --mode=mshot 多鏡一次生成(長 prompt 分鏡,241f)
用法: ltx25_run.py <podId> --mode=... [--prompt-file=] [--first= --last=] [--out=] [--seed=] [--frames=121]
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

KF = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
UNET = "ltx-2.5-22b-distilled-transformer-nvfp4.safetensors"
TE = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
VVAE, AVAE = "ltx-2.5-video-vae-conv-bf16.safetensors", "ltx-2.5-audio-vae-bf16.safetensors"
UPS = "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
SIG1 = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
SIG2 = "0.85, 0.7250, 0.4219, 0.0"

STYLE = ("Photorealistic live-action martial-arts film still, night boxing arena, cool white overhead "
         "spotlights forming a bright pool on the blue canvas, warm golden corner rim lights, hazy air, "
         "dark blurred crowd beyond the ropes. ")
CAST = ("A young Chinese woman in a mini-length deep-red gold-embroidered silk qipao, bare-handed, fights "
        "a towering realistic anthropomorphic giant panda in a white taekwondo dobok with a blue belt and "
        "red boxing gloves. EXACTLY ONE woman and EXACTLY ONE panda. ")
NEG = "blurry, distorted, cartoon, extra limbs, duplicated characters, text, watermark, logo, speech, talking"


def stage(g, pfx, model_ref, latent_ref, pos, neg, sigmas, seed):
    g[pfx + "noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g[pfx + "guider"] = {"class_type": "CFGGuider",
                         "inputs": {"model": model_ref, "positive": pos, "negative": neg, "cfg": 1.0}}
    g[pfx + "samp"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    g[pfx + "sig"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
    g[pfx + "run"] = {"class_type": "SamplerCustomAdvanced",
                      "inputs": {"noise": [pfx + "noise", 0], "guider": [pfx + "guider", 0],
                                 "sampler": [pfx + "samp", 0], "sigmas": [pfx + "sig", 0],
                                 "latent_image": latent_ref}}
    return [pfx + "run", 0]


def build(mode, prompt, first, last, seed, out, W=960, H=544, FR=121, fps=24):
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": TE, "type": "ltxv", "device": "default"}},
        "vvae": {"class_type": "VAELoader", "inputs": {"vae_name": VVAE}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": AVAE}},
        "ups": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": UPS}},
        "pos0": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}},
        "neg0": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEG}},
        "cond": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos0", 0], "negative": ["neg0", 0], "frame_rate": float(fps)}},
        "vlat": {"class_type": "EmptyLTXVLatentVideo",
                 "inputs": {"width": W, "height": H, "length": FR, "batch_size": 1}},
        "alat": {"class_type": "LTXVEmptyLatentAudio",
                 "inputs": {"frames_number": FR, "frame_rate": fps, "batch_size": 1, "audio_vae": ["avae", 0]}},
        # inp2 的 image 為必填但 bypass=True 時不參與(t2v/flf2v 引導都不走這口)
        "dummy": {"class_type": "EmptyImage", "inputs": {"width": 64, "height": 64, "batch_size": 1, "color": 0}},
    }
    pos, neg = ["cond", 0], ["cond", 1]
    vref = ["vlat", 0]
    if mode == "flf2v":
        for tag, fn, idx in (("f0", first, 0), ("f1", last, -1)):
            g["ld" + tag] = {"class_type": "LoadImage", "inputs": {"image": fn}}
            g["pp" + tag] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["ld" + tag, 0], "img_compression": 18}}
            g["ag" + tag] = {"class_type": "LTXVAddGuide",
                            "inputs": {"positive": pos, "negative": neg, "vae": ["vvae", 0],
                                       "latent": vref, "image": ["pp" + tag, 0],
                                       "frame_idx": idx, "strength": 1.0}}
            pos, neg, vref = ["ag" + tag, 0], ["ag" + tag, 1], ["ag" + tag, 2]
    g["cat"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": vref, "audio_latent": ["alat", 0]}}
    s1 = stage(g, "s1", ["unet", 0], ["cat", 0], pos, neg, SIG1, seed)
    g["sep1"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": s1}}
    # 第二段:latent 2x + 3 步精修
    g["up2"] = {"class_type": "LTXVLatentUpsampler",
                "inputs": {"samples": ["sep1", 0], "upscale_model": ["ups", 0], "vae": ["vvae", 0]}}
    g["inp2"] = {"class_type": "LTXVImgToVideoInplace",
                 "inputs": {"vae": ["vvae", 0], "image": ["dummy", 0], "latent": ["up2", 0],
                            "strength": 1.0, "bypass": True}}
    g["cat2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["inp2", 0], "audio_latent": ["sep1", 1]}}
    s2 = stage(g, "s2", ["unet", 0], ["cat2", 0], pos, neg, SIG2, seed + 1)
    g["sep2"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": s2}}
    if mode == "flf2v":
        g["crop"] = {"class_type": "LTXVCropGuides",
                     "inputs": {"positive": pos, "negative": neg, "latent": ["sep2", 0]}}
        vout = ["crop", 2]
    else:
        vout = ["sep2", 0]
    g["vdec"] = {"class_type": "VAEDecodeTiled",
                 "inputs": {"samples": vout, "vae": ["vvae", 0], "tile_size": 512,
                            "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    g["adec"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["sep2", 1], "audio_vae": ["avae", 0]}}
    g["mk"] = {"class_type": "CreateVideo", "inputs": {"images": ["vdec", 0], "audio": ["adec", 0], "fps": float(fps)}}
    g["sv"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": out, "format": "mp4", "codec": "h264"}}
    return g


def main():
    pid = sys.argv[1]
    o = {"mode": "t2v", "prompt-file": "", "first": "", "last": "", "out": "ltx_t2v",
         "seed": "5001", "frames": "121", "fps": "24"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    if o["prompt-file"]:
        prompt = open(os.path.expanduser(o["prompt-file"])).read().strip()
    else:
        prompt = STYLE + CAST + "They circle each other exchanging probing strikes, dynamic camera. Arena crowd noise and impact sounds."
    first = last = ""
    if o["mode"] == "flf2v":
        first = T.upload(pid, os.path.join(KF, o["first"]))
        last = T.upload(pid, os.path.join(KF, o["last"]))
    g = build(o["mode"], prompt, first, last, int(o["seed"]), o["out"],
              FR=int(o["frames"]), fps=int(o["fps"]))
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "ltx-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:1200]); sys.exit(1)
    print(f"SUBMITTED mode={o['mode']}", flush=True)
    t0 = time.time(); miss = 0
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
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:1200]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        print(f"  running {(time.time()-t0)/60:.1f}min", flush=True)
        if time.time() - t0 > 3000: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
