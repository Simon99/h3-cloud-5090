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
W = int(os.environ.get("GW", "640")); H = int(os.environ.get("GH", "384"))     # small for fast debug
FR = int(os.environ.get("GF", "56")); STEPS = int(os.environ.get("GSTEPS", "20"))
NSHOTS = int(os.environ.get("GN", "1"))   # how many shots (1 for debug)
USE_SPECTRUM = os.environ.get("GSPECTRUM", "0") == "1"   # wire Spectrum accel node if installed
TAG = os.environ.get("GTAG", "")          # suffix for the SaveVideo prefix (A/B labelling)
SPEC = None                                # discovered Spectrum node spec (class + model-input key), set in main

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

def _default_for(spec):
    """Best-effort default value for a ComfyUI input schema entry [type, {cfg}]."""
    t = spec[0] if spec else None
    cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if isinstance(t, list):                       # combo/enum: [values...]
        return cfg.get("default", t[0] if t else None)
    if "default" in cfg:
        return cfg["default"]
    return {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False, "STRING": ""}.get(t, None)

def discover_spectrum(oi):
    """Find the Spectrum-MiniMax-H3 node in object_info; return (class, model_key, inputs_template) or None."""
    for cls, info in oi.items():
        if "spectrum" not in cls.lower():
            continue
        req = info.get("input", {}).get("required", {})
        opt = info.get("input", {}).get("optional", {})
        model_key = next((k for k, s in {**req, **opt}.items() if s and s[0] == "MODEL"), None)
        if not model_key:
            continue
        ins = {k: _default_for(s) for k, s in req.items() if s and s[0] != "MODEL"}   # fill required (non-model) defaults
        # observability / memory params if the node exposes them
        for k in ("debug",):
            if k in req or k in opt: ins[k] = True
        for k in ("history_storage",):
            if k in req or k in opt: ins[k] = "system_ram"
        return (cls, model_key, ins)
    return None

def build(prompt, seed, prefix):
    g = {
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
    if USE_SPECTRUM and SPEC:
        cls, model_key, ins = SPEC
        node_ins = dict(ins); node_ins[model_key] = ["L_model", 0]   # UNETLoader -> Spectrum
        g["SPEC"] = {"class_type": cls, "inputs": node_ins}
        g["guider"]["inputs"]["model"] = ["SPEC", 0]                  # Spectrum -> Guider + Scheduler
        g["sched"]["inputs"]["model"] = ["SPEC", 0]
    return g

def run(prefix, prompt, seed):
    wf = build(prompt, seed, prefix)
    req = urllib.request.Request(SRV + "/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        pid = json.load(urllib.request.urlopen(req, timeout=30))["prompt_id"]
    except urllib.error.HTTPError as e:
        print("SUBMIT_ERR", prefix, e.read().decode()[:900]); return
    print("SHOT_START %s pid=%s res=%dx%d frames=%d steps=%d spectrum=%s" % (prefix, pid, W, H, FR, STEPS, bool(USE_SPECTRUM and SPEC)))
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
    # print the exact schemas of the nodes we use (helps diagnose validation errors)
    try:
        oi = json.load(urllib.request.urlopen(SRV + "/object_info", timeout=20))
        for n in ("UNETLoader", "CLIPLoader", "MiniMaxH3ImageToVideo", "CreateVideo"):
            info = oi.get(n, {}).get("input", {})
            req = list(info.get("required", {}).keys()); opt = list(info.get("optional", {}).keys())
            print("SCHEMA %s required=%s optional=%s" % (n, req, opt))
        # discover the Spectrum accel node (name is unknown until installed)
        spec_keys = [k for k in oi if "spectrum" in k.lower()]
        print("SPECTRUM_NODES_PRESENT=%s" % spec_keys)
        if USE_SPECTRUM:
            SPEC = discover_spectrum(oi)
            if SPEC:
                cls, mk, ins = SPEC
                print("SPECTRUM_WIRED class=%s model_key=%s inputs=%s" % (cls, mk, json.dumps(ins, ensure_ascii=False)))
            else:
                print("SPECTRUM_NOT_FOUND (requested but node absent) -> running WITHOUT spectrum")
    except Exception as e:
        print("SCHEMA_ERR", e)
    tag = ("_" + TAG) if TAG else ""
    for i, (pfx, pr) in enumerate(SHOTS[:NSHOTS]):
        run("cloudtest_" + pfx + tag, pr, 2000 + i)
    print("ALL_SHOTS_DONE")
