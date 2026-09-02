#!/usr/bin/env python3
"""Wan-on-5090 統一跑手(接線全取自官方 workflow_templates,blueprint-first)。
模式:
  --mode=scail  SCAIL-2 替換式角色動畫(委派 scail_run.build)
  --mode=t2v    A14B 高低噪雙專家 T2V(--fast=1 用 4步 lightx2v LoRA,否則 20步 cfg3.5)
  --mode=flf    A14B I2V 首尾幀(--first/--last;--fast=1 4步)
用法: wan5090_run.py <podId> --mode=... [各模式參數] [--seed=] [--out=]
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T
import scail_run

KF = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
UMT5 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WVAE = "wan_2.1_vae.safetensors"
T2V_HI = "Wan2.2-T2V-A14B_NVFP4_Sparse_high_comfy.safetensors"
T2V_LO = "Wan2.2-T2V-A14B_NVFP4_Sparse_low_comfy.safetensors"
I2V_HI = "Wan2.2-I2V-A14B_NVFP4_Sparse_high_comfy.safetensors"
I2V_LO = "Wan2.2-I2V-A14B_NVFP4_Sparse_low_comfy.safetensors"
LORA_T = ("wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
          "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors")
LORA_I = ("wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
          "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")

STYLE = ("Photorealistic live-action martial-arts film still, night boxing arena, cool white overhead "
         "spotlights, warm golden corner rim lights, hazy air, dark blurred crowd beyond the ropes. ")
CAST = ("A young Chinese woman in a mini-length deep-red gold-embroidered silk qipao, bare-handed, fights "
        "a towering realistic anthropomorphic giant panda in a white taekwondo dobok with a blue belt. "
        "EXACTLY ONE woman and EXACTLY ONE panda, both fully visible. ")
NEG = ("色调艳丽,过曝,静态,细节模糊不清,字幕,风格,作品,画作,画面,静止,整体发灰,最差质量,低质量,"
       "JPEG压缩残留,丑陋的,残缺的,多余的手指,画得不好的手部,画得不好的脸部,畸形的,毁容的,"
       "形态畸形的肢体,手指融合,静止不动的画面,杂乱的背景,三条腿,背景人很多,倒着走")


def dual_expert(g, hi, lo, lora_pair, fast, pos, neg, lat, seed, shift):
    """官方 A14B 雙專家接力:高噪 0→切點、低噪 切點→尾;fast=4步cfg1+LoRA,否則20步cfg3.5。"""
    steps, cfg, mid = (4, 1.0, 2) if fast else (20, 3.5, 10)
    g["unH"] = {"class_type": "UNETLoader", "inputs": {"unet_name": hi, "weight_dtype": "default"}}
    g["unL"] = {"class_type": "UNETLoader", "inputs": {"unet_name": lo, "weight_dtype": "default"}}
    mh, ml = ["unH", 0], ["unL", 0]
    if fast:
        g["loH"] = {"class_type": "LoraLoaderModelOnly",
                    "inputs": {"model": mh, "lora_name": lora_pair[0], "strength_model": 1.0}}
        g["loL"] = {"class_type": "LoraLoaderModelOnly",
                    "inputs": {"model": ml, "lora_name": lora_pair[1], "strength_model": 1.0}}
        mh, ml = ["loH", 0], ["loL", 0]
    g["msH"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": mh, "shift": shift}}
    g["msL"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ml, "shift": shift}}
    g["kA"] = {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["msH", 0], "add_noise": "enable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                          "positive": pos, "negative": neg, "latent_image": lat,
                          "start_at_step": 0, "end_at_step": mid, "return_with_leftover_noise": "enable"}}
    g["kB"] = {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["msL", 0], "add_noise": "disable", "noise_seed": 0,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                          "positive": pos, "negative": neg, "latent_image": ["kA", 0],
                          "start_at_step": mid, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
    return ["kB", 0]


def build_t2v(o):
    seed, fast = int(o["seed"]), o["fast"] == "1"
    W, H, FR = int(o["w"]), int(o["h"]), int(o["frames"])
    prompt = STYLE + CAST + "They circle each other exchanging probing strikes, dynamic camera."
    g = {
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": UMT5, "type": "wan", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": WVAE}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEG}},
        "lat": {"class_type": "EmptyHunyuanLatentVideo",
                "inputs": {"width": W, "height": H, "length": FR, "batch_size": 1}},
    }
    out = dual_expert(g, T2V_HI, T2V_LO, LORA_T, fast, ["pos", 0], ["neg", 0], ["lat", 0], seed, 5.0)
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": out, "vae": ["vae", 0]}}
    g["mk"] = {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "fps": 16.0}}
    g["sv"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": o["out"], "format": "mp4", "codec": "h264"}}
    return g


def build_flf(pid, o):
    seed, fast = int(o["seed"]), o["fast"] == "1"
    W, H, FR = int(o["w"]), int(o["h"]), int(o["frames"])
    first = T.upload(pid, os.path.join(KF, o["first"]))
    last = T.upload(pid, os.path.join(KF, o["last"]))
    prompt = STYLE + CAST + o.get("action", "A fierce exchange of martial-arts strikes.")
    shift = 5.0 if fast else 8.0
    g = {
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": UMT5, "type": "wan", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": WVAE}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEG}},
        "im1": {"class_type": "LoadImage", "inputs": {"image": first}},
        "im2": {"class_type": "LoadImage", "inputs": {"image": last}},
        "flf": {"class_type": "WanFirstLastFrameToVideo",
                "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
                           "width": W, "height": H, "length": FR, "batch_size": 1,
                           "start_image": ["im1", 0], "end_image": ["im2", 0]}},
    }
    out = dual_expert(g, I2V_HI, I2V_LO, LORA_I, fast, ["flf", 0], ["flf", 1], ["flf", 2], seed, shift)
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": out, "vae": ["vae", 0]}}
    g["mk"] = {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "fps": 16.0}}
    g["sv"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": o["out"], "format": "mp4", "codec": "h264"}}
    return g


def main():
    pid = sys.argv[1]
    o = {"mode": "t2v", "seed": "9001", "out": "wan_a", "fast": "1", "w": "832", "h": "480",
         "frames": "81", "first": "", "last": "", "action": "",
         # scail 轉傳參數
         "video": "", "ref": ("/tmp/claude-1000/-home-simon-claude-sandboxes-director/"
                              "cf5c4cdc-a1be-492f-a8ef-db4a00fe2647/scratchpad/ref_duo_full.png"),
         "start": "0", "fps": "24", "drive-prompt": "person", "ref-prompt": "person. panda."}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    for k in ("ref-prompt", "drive-prompt", "action"):
        o[k] = o[k].replace("+", " ")   # 批次檔不能帶空白,以 + 代替
    if o["mode"] == "scail":
        vidname = T.upload(pid, os.path.expanduser(o["video"]))
        refname = T.upload(pid, os.path.expanduser(o["ref"]))
        g = scail_run.build(vidname, refname, o)
    elif o["mode"] == "flf":
        g = build_flf(pid, o)
    else:
        g = build_t2v(o)
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "wn-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job or r.get("node_errors"):
        # node_errors 非空=部分輸出被驗證忽略(如 min 值違規),會變成「假成功」——一律判提交失敗
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:1200]); sys.exit(1)
    print(f"SUBMITTED mode={o['mode']} job={job}", flush=True)
    t0 = time.time(); miss = 0
    while True:
        time.sleep(20)
        try: os.utime("/tmp/rp-lease-heartbeat", None)
        except Exception: pass
        try:
            h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60)); miss = 0
        except Exception:
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
        if time.time() - t0 > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
