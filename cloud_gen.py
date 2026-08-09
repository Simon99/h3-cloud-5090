#!/usr/bin/env python3
"""Generate H3 bear test shots on the pod's ComfyUI (localhost:8188), time each.
Adapted from the proven local gen_shots.py graph: UNETLoader+CLIPLoader (safetensors) +
MiniMaxH3ImageToVideo + sampler chain + dual VAE decode + CreateVideo + SaveVideo.
No Spectrum node (not installed on the pod); guider/scheduler use the UNET model directly.
Env: GW/GH/GF/GSTEPS override res/frames/steps.
"""
import json, sys, time, urllib.request, os

SRV = "http://127.0.0.1:8188"
UNET = "minimax_h3_fl2va_pruned_fp8_scaled.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VVAE = "minimax_h3_video_vae_fp16.safetensors"
AVAE = "minimax_h3_audio_vae_fp32.safetensors"
W = int(os.environ.get("GW", "1312")); H = int(os.environ.get("GH", "736"))
FR = int(os.environ.get("GF", "141")); STEPS = int(os.environ.get("GSTEPS", "20"))

SHOTS = [
 ("bear11_water",
  "A Formosan black bear wading and swimming across a clear shallow mountain stream, water rippling around its body, "
  "green mossy banks, slow steady tracking shot. Photorealistic wildlife documentary, National Geographic quality. "
  "No people, no on-screen text, no subtitles, no captions. Slow steady tracking, no fast camera movement.\n\n"
  "Audio: splashing and flowing stream water, forest ambience, no voices, no speech, no music."),
 ("bear15_forest",
  "Sweeping aerial over the vast primary forest of the Central Mountain Range, endless green ridges rolling under "
  "drifting clouds, slow majestic glide. Photorealistic wildlife documentary, National Geographic quality. "
  "No people, no on-screen text, no subtitles, no captions. Slow majestic glide, no fast camera movement.\n\n"
  "Audio: high mountain wind, vast and calm, no voices, no speech, no music."),
]

def build(prompt, seed, prefix):
    return {
      "L_model": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
      "L_clip":  {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "minimax"}},
      "L_vvae":  {"class_type": "VAELoader", "inputs": {"vae_name": VVAE}},
      "L_avae":  {"class_type": "VAELoader", "inputs": {"vae_name": AVAE}},
      "H3": {"class_type": "MiniMaxH3ImageToVideo",
             "inputs": {"clip": ["L_clip", 0], "vae": ["L_vvae", 0],
                        "prompt": prompt, "width": W, "height": H, "length": FR}},
      "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
      "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
      "guider": {"class_type": "BasicGuider", "inputs": {"model": ["L_model", 0], "conditioning": ["H3", 0]}},
      "sched": {"class_type": "BasicScheduler",
                "inputs": {"model": ["L_model", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0}},
      "ksamp": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guider", 0],
                           "sampler": ["sampler", 0], "sigmas": ["sched", 0], "latent_image": ["H3", 1]}},
      "vdec": {"class_type": "VAEDecode", "inputs": {"samples": ["ksamp", 0], "vae": ["L_vvae", 0]}},
      "adec": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["ksamp", 0], "vae": ["L_avae", 0]}},
      "mkvid": {"class_type": "CreateVideo", "inputs": {"images": ["vdec", 0], "audio": ["adec", 0], "fps": 24.0}},
      "save": {"class_type": "SaveVideo",
               "inputs": {"video": ["mkvid", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }

def run(prefix, prompt, seed):
    wf = build(prompt, seed, prefix)
    req = urllib.request.Request(SRV + "/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        pid = json.load(urllib.request.urlopen(req, timeout=30))["prompt_id"]
    except urllib.error.HTTPError as e:
        print("SUBMIT_ERR", prefix, e.read().decode()[:900]); return
    print("SHOT_START %s pid=%s res=%dx%d frames=%d steps=%d" % (prefix, pid, W, H, FR, STEPS))
    t0 = time.time()
    while True:
        time.sleep(5)
        try:
            h = json.load(urllib.request.urlopen(f"{SRV}/history/{pid}", timeout=20))
        except Exception:
            continue
        if pid in h:
            st = h[pid]["status"]
            if st.get("status_str") == "error":
                print("RUN_ERR %s %s" % (prefix, json.dumps(st.get("messages", [])[-4:], ensure_ascii=False)[:1400])); return
            if st.get("completed"):
                dt = time.time() - t0
                outs = h[pid].get("outputs", {})
                files = [g.get("filename") for o in outs.values() for g in o.get("gifs", []) + o.get("videos", [])]
                print("SHOT_DONE %s in %.1fs (%.2fs/frame) files=%s" % (prefix, dt, dt / FR, files))
                return
        if time.time() - t0 > 2400:
            print("SHOT_TIMEOUT %s" % prefix); return

if __name__ == "__main__":
    for i, (pfx, pr) in enumerate(SHOTS):
        run("cloudtest_" + pfx, pr, 2000 + i)
    print("ALL_SHOTS_DONE")
