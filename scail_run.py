#!/usr/bin/env python3
"""SCAIL-2 替換式角色動畫跑手(接線取自官方 character_replacement_scail_2_base blueprint)。
駕駛片雙人 → SAM3 追蹤 → SCAIL2ColoredMask 確定性綁定 → WanSCAILToVideo(replacement)。
快速模式:DPO LoRA 1.0 + lightx2v 蒸餾 LoRA 0.8 + 6 步 cfg1 euler/simple + shift5。
用法: scail_run.py <podId> --video=<駕駛mp4> [--ref=<參考圖>] [--seed=N] [--out=name]
      [--frames=81] [--fps=24] [--drive-prompt=person] [--ref-prompt="person. panda."]
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

SCAIL = "wan2.1_14B_SCAIL_2_nvfp4_mxpf8_mix.safetensors"
DPO = "wan2.1_SCAIL_2_DPO_lora_bf16.safetensors"
DIST = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
SAM3 = "sam3.1_multiplex_fp16.safetensors"
UMT5 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WVAE = "wan_2.1_vae.safetensors"
CVH = "clip_vision_h.safetensors"
W, H = 896, 512

POS = ("The person on the left is a young Chinese woman in a mini-length deep-red gold-embroidered "
       "silk qipao with a gold hairpin in her high bun, bare-handed. The person on the right is a "
       "towering realistic anthropomorphic giant panda in a white taekwondo dobok with a blue belt. "
       "They fight in a boxing ring at night, cool white overhead spotlights, warm golden corner rim "
       "lights, hazy air, dark blurred crowd beyond the ropes. Photorealistic live-action "
       "martial-arts film, cinematic lighting.")
NEG = "blurry, distorted, cartoon, extra limbs, duplicated characters, text, watermark, logo"


def build(vidname, refname, o):
    fr = int(o["frames"]); seed = int(o["seed"])
    g = {
        # ── 駕駛片 → 幀 → 縮放 ──
        "lv": {"class_type": "LoadVideo", "inputs": {"file": vidname}},
        "gv": {"class_type": "GetVideoComponents", "inputs": {"video": ["lv", 0]}},
        "fb": {"class_type": "ImageFromBatch",
               "inputs": {"image": ["gv", 0], "batch_index": int(o["start"]), "length": fr}},
        "rz": {"class_type": "ImageScale",
               "inputs": {"image": ["fb", 0], "upscale_method": "area",
                          "width": W, "height": H, "crop": "center"}},
        # ── SAM3 雙路追蹤(駕駛片與參考圖共用一顆 checkpoint)──
        "s3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SAM3}},
        "cdD": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["s3", 1], "text": o["drive-prompt"]}},
        "tkD": {"class_type": "SAM3_VideoTrack",
                "inputs": {"images": ["rz", 0], "model": ["s3", 0], "conditioning": ["cdD", 0],
                           "detection_threshold": 0.5, "max_objects": 4, "detect_interval": 1}},
        "ldR": {"class_type": "LoadImage", "inputs": {"image": refname}},
        "cdR": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["s3", 1], "text": o["ref-prompt"]}},
        "tkR": {"class_type": "SAM3_VideoTrack",
                "inputs": {"images": ["ldR", 0], "model": ["s3", 0], "conditioning": ["cdR", 0],
                           "detection_threshold": 0.5, "max_objects": 4, "detect_interval": 1}},
        "cm": {"class_type": "SCAIL2ColoredMask",
               "inputs": {"driving_track_data": ["tkD", 0], "ref_track_data": ["tkR", 0],
                          "object_indices": "", "sort_by": "left_to_right", "replacement_mode": True}},
        # 綁定可視化(下載驗證用)
        "svm1": {"class_type": "SaveImage", "inputs": {"images": ["cm", 0], "filename_prefix": o["out"] + "_maskD"}},
        "svm2": {"class_type": "SaveImage", "inputs": {"images": ["cm", 1], "filename_prefix": o["out"] + "_maskR"}},
        # ── 條件與 SCAIL 節點 ──
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": UMT5, "type": "wan", "device": "default"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": POS}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEG}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": WVAE}},
        "cvl": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CVH}},
        "cve": {"class_type": "CLIPVisionEncode",
                "inputs": {"clip_vision": ["cvl", 0], "image": ["ldR", 0], "crop": "none"}},
        "sc": {"class_type": "WanSCAILToVideo",
               "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
                          "width": W, "height": H, "length": fr, "batch_size": 1,
                          "pose_strength": 1.0, "pose_start": 0.0, "pose_end": 1.0,
                          "video_frame_offset": 0, "previous_frame_count": 5,
                          "pose_video": ["rz", 0], "pose_video_mask": ["cm", 0],
                          "replacement_mode": True, "reference_image": ["ldR", 0],
                          "reference_image_mask": ["cm", 1], "clip_vision_output": ["cve", 0]}},
        # ── 模型鏈:SCAIL nvfp4 → DPO 1.0 → 蒸餾 0.8 → shift5 → 6步 cfg1 ──
        "un": {"class_type": "UNETLoader", "inputs": {"unet_name": SCAIL, "weight_dtype": "default"}},
        "lo1": {"class_type": "LoraLoaderModelOnly",
                "inputs": {"model": ["un", 0], "lora_name": DPO, "strength_model": 1.0}},
        "lo2": {"class_type": "LoraLoaderModelOnly",
                "inputs": {"model": ["lo1", 0], "lora_name": DIST, "strength_model": 0.8}},
        "ms": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["lo2", 0], "shift": 5.0}},
        "ks": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "sig": {"class_type": "BasicScheduler",
                "inputs": {"model": ["lo2", 0], "scheduler": "simple", "steps": 6, "denoise": 1.0}},
        "samp": {"class_type": "SamplerCustom",
                 "inputs": {"model": ["ms", 0], "add_noise": True, "noise_seed": seed, "cfg": 1.0,
                            "positive": ["sc", 0], "negative": ["sc", 1],
                            "sampler": ["ks", 0], "sigmas": ["sig", 0], "latent_image": ["sc", 2]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["samp", 1], "vae": ["vae", 0]}},
        "mk": {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "fps": float(o["fps"])}},
        "sv": {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": o["out"], "format": "mp4", "codec": "h264"}},
    }
    return g


def main():
    pid = sys.argv[1]
    o = {"video": "", "ref": os.path.expanduser(
            "/tmp/claude-1000/-home-simon-claude-sandboxes-director/"
            "cf5c4cdc-a1be-492f-a8ef-db4a00fe2647/scratchpad/ref_duo_full.png"),
         "seed": "8001", "out": "scail_a", "frames": "81", "start": "0", "fps": "24",
         "drive-prompt": "person", "ref-prompt": "person. panda."}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    vidname = T.upload(pid, os.path.expanduser(o["video"]))
    refname = T.upload(pid, os.path.expanduser(o["ref"]))
    g = build(vidname, refname, o)
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "sc-" + uuid.uuid4().hex[:8]})
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
