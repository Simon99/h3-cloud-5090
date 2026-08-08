#!/usr/bin/env python3
"""Drive one H3 T2V generation on the pod's ComfyUI, from the official api template.
--inspect : print the template's node structure (to see what to patch)
(default) : patch our downloaded model filenames + prompt + 720p + frames, POST, poll, time it.
Env overrides: GP=prompt GW=width GH=height GF=frames
"""
import json, sys, os, time, urllib.request, glob

SRV = "http://127.0.0.1:8188"
TPL = glob.glob("/usr/local/lib/python*/dist-packages/comfyui_workflow_templates_json/templates/api_minimax_h3_t2v.json")[0]
MODELS = "/workspace/ComfyUI/models"
wf = json.load(open(TPL))
wf = wf.get("prompt", wf)   # api format may wrap under "prompt"

def have(sub, *needles):
    for f in os.listdir(os.path.join(MODELS, sub)):
        if all(n in f for n in needles) and f.endswith(".safetensors"):
            return f
    return None

if "--inspect" in sys.argv:
    for k, v in wf.items():
        if isinstance(v, dict) and "class_type" in v:
            ins = {kk: ("<link>" if isinstance(vv, list) else vv) for kk, vv in v.get("inputs", {}).items()}
            print("NODE %-4s %-30s %s" % (k, v["class_type"], json.dumps(ins, ensure_ascii=False)[:240]))
    sys.exit()

# our actually-downloaded filenames
DIFF = have("diffusion_models", "fl2va") or have("diffusion_models", "ref2va")
ENC  = have("text_encoders", "qwen3vl")
VVAE = have("vae", "video_vae")
AVAE = have("vae", "audio_vae")
print("OURS diff=%s enc=%s vvae=%s avae=%s" % (DIFF, ENC, VVAE, AVAE))

PROMPT = os.environ.get("GP", "A Formosan black bear walks slowly through a misty mountain forest at dawn, cinematic wildlife documentary, soft light.")
W = int(os.environ.get("GW", "1312")); H = int(os.environ.get("GH", "736")); FR = int(os.environ.get("GF", "141"))

for k, v in wf.items():
    if not isinstance(v, dict): continue
    ct = v.get("class_type", ""); ins = v.get("inputs", {})
    for key, val in list(ins.items()):
        if isinstance(val, str) and val.endswith(".safetensors"):
            lv = val.lower()
            if "fl2va" in lv or "ref2va" in lv: ins[key] = DIFF
            elif "qwen" in lv: ins[key] = ENC
            elif "video_vae" in lv: ins[key] = VVAE
            elif "audio_vae" in lv: ins[key] = AVAE
        if key in ("text",) and isinstance(val, str) and len(val) > 3 and "negative" not in ct.lower():
            ins[key] = PROMPT
        if key == "width": ins[key] = W
        if key == "height": ins[key] = H
        if key in ("length", "num_frames", "frames"): ins[key] = FR
        if key == "filename_prefix": ins[key] = "pod_test"
        if key in ("seed", "noise_seed"): ins[key] = 42

req = urllib.request.Request(SRV + "/prompt", data=json.dumps({"prompt": wf}).encode(),
                             headers={"Content-Type": "application/json"})
try:
    pid = json.load(urllib.request.urlopen(req, timeout=30))["prompt_id"]
except urllib.error.HTTPError as e:
    print("SUBMIT_ERROR", e.read().decode()[:900]); sys.exit(1)
print("SUBMITTED", pid, "res", W, "x", H, "frames", FR)
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
            print("RUN_ERROR", json.dumps(st.get("messages", [])[-4:], ensure_ascii=False)[:1200]); break
        if st.get("completed"):
            outs = h[pid].get("outputs", {})
            print("DONE_IN %.1fs" % (time.time() - t0))
            for n, o in outs.items():
                for g in o.get("gifs", []) + o.get("videos", []): print("FILE", g.get("filename"), g.get("subfolder"))
            break
    if time.time() - t0 > 1800:
        print("TIMEOUT"); break
