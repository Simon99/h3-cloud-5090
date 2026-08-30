#!/usr/bin/env python3
"""REF2VA 單鏡實跑:上傳參考圖 → 組 workflow → 送生成 → 輪詢 → 取回。
用法: ref2va_run.py <podId> [--size match|max] [--out name] [--seed N]
"""
import json, mimetypes, os, sys, time, urllib.request, uuid

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _get(url, timeout=60):
    """帶瀏覽器 UA 的 GET——RunPod proxy 會擋 python-urllib 預設 UA(403)"""
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)

REFS = os.path.expanduser("~/claude-sandboxes/director/research/experiments/nightmarket-consistency/refs")
UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VVAE, AVAE = "minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"
W, H, FR, STEPS = 1312, 736, 141, 20

CHAR = ("a Taiwanese street-food vendor in her forties, round face, navy headscarf over a low bun, "
        "white short-sleeve polo with rolled cuffs, faded indigo denim bib apron with shoulder straps, "
        "pale green jade bangle, small gold earrings, warm mid-tone skin with visible nasolabial folds")

AHAO = ("a muscular Taiwanese street-food vendor in his early thirties, buzz-cut hair under a black sweatband, "
        "square jaw with short stubble, white fitted sleeveless tank top, dark grey waist-tied work apron, "
        "a Japanese wave tattoo down his left forearm, small silver earring, white towel around his neck, "
        "black rubber boots, tanned athletic build with broad shoulders")

SCENES_AHAO = {
  "prep": ("scene-mianxian-prep.png",
    "in the old apartment kitchen shown in <Picture 3>. He stands at the stainless work bench, "
    "cutting braised pork intestine into segments with kitchen scissors over a steel basin, "
    "the braising pan of dark sauce beside him, morning light from the window"),
  "night": ("scene-mianxian-night.png",
    "at the night-market mianxian stall shown in <Picture 3>. He ladles thick orange-brown "
    "vermicelli soup from the big steel vat into a white bowl, steam billowing up past the bare bulbs, "
    "neon of the lane glowing behind him"),
}

YUN = ("a slight young Taiwanese woman in her early twenties, round face with single-fold eyelids and dimples, "
       "thin gold round-frame glasses, dark chestnut hair in two low braids tied with mustard-yellow yarn, "
       "cream chunky hand-knit sweater with rolled cuffs, dark brown canvas bib apron with crochet hooks in the pocket, "
       "dark green plaid long skirt, brown ankle boots with grey socks, "
       "a band of multicoloured yarn wrapped around her left wrist")

SCENES_YUN = {
  "studio": ("scene-knit-studio.png",
    "in the small home craft studio shown in <Picture 3>. She sits at the light wooden table by the window, "
    "crocheting a half-finished knitted doll, yarn balls and hooks spread around her, "
    "warm afternoon light falling across the table"),
  "market": ("scene-craft-market.png",
    "at the weekend craft-market stall shown in <Picture 3>. She stands behind the linen-covered table "
    "arranging her handmade knitted dolls, adjusting one on a small wooden box, "
    "late afternoon golden light slanting under the canvas awning"),
  "handover": ("scene-craft-market.png",
    "at the craft-market stall shown in <Picture 3>. She lifts a small cream knitted rabbit from the table "
    "and holds it out toward the camera with both hands, smiling shyly, "
    "the hanging dolls on the wooden rack softly out of focus behind her"),
}

SCENES = {
  "kitchen": ("scene-home-prep.png",
    "in the old apartment kitchen shown in <Picture 3>. She stands at the stainless-topped prep bench, "
    "chopping cabbage on a round wooden block with a heavy cleaver, calm and focused, "
    "afternoon light raking in from the aluminium window on the left"),
  "night": ("scene-nightmarket-night.png",
    "at the night-market stall shown in <Picture 3>. She works behind the hot steel griddle, "
    "turning cabbage and pork with a long metal spatula, steam rising through the overhead bulbs, "
    "neon signs of the lane glowing behind her"),
  "dusk": ("scene-nightmarket-empty-cart.png",
    "at the stall shown in <Picture 3> during the blue hour. She wipes down the steel griddle and "
    "sets out sauce bottles and plates, getting ready to open, the lane still quiet behind her"),
}


def make_prompt(scene, with_char):
    if scene in SCENES_AHAO: tbl, who_desc = SCENES_AHAO, AHAO
    elif scene in SCENES_YUN: tbl, who_desc = SCENES_YUN, YUN
    else: tbl, who_desc = SCENES, CHAR
    _, act = tbl[scene]
    subj = "man" if scene in SCENES_AHAO else "woman"  # 阿豪男、其餘女
    who = (f"The {subj} shown in <Picture 1> and <Picture 2> — " + who_desc + " — works "
           if with_char else f"A {subj} — " + who_desc + " — works ")
    if not with_char:
        act = act.replace("shown in <Picture 3>", "").replace("  ", " ")
    return ("Photorealistic documentary cinematography, natural light. " + who + act + ". "
            "Slow gentle push-in, no fast camera movement. "
            "No people speaking, no on-screen text, no subtitles, no captions.")


def base(pid): return f"https://{pid}-8188.proxy.runpod.net"


def post_json(url, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def upload(pid, path):
    """multipart 上傳到 ComfyUI /upload/image"""
    bnd = "----" + uuid.uuid4().hex
    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "image/png"
    body = b""
    body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n".encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode() + open(path, "rb").read() + b"\r\n"
    body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode()
    body += f"--{bnd}--\r\n".encode()
    req = urllib.request.Request(base(pid) + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={bnd}",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    print(f"  uploaded {name} → {d.get('name')}")
    return d["name"]


def build(names, size_mode, seed, prefix):
    PROMPT_HOLDER = PROMPT
    g = {
        "L_model": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "L_clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "minimax"}},
        "L_vvae": {"class_type": "VAELoader", "inputs": {"vae_name": VVAE}},
        "L_avae": {"class_type": "VAELoader", "inputs": {"vae_name": AVAE}},
        "R2V": {"class_type": "MiniMaxH3ReferenceToVideo",
                "inputs": {"clip": ["L_clip", 0], "vae": ["L_vvae", 0], "audio_vae": ["L_avae", 0],
                           "prompt": PROMPT_HOLDER, "width": W, "height": H, "length": FR,
                           "ref_image_size": size_mode}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "guider": {"class_type": "BasicGuider", "inputs": {"model": ["L_model", 0], "conditioning": ["R2V", 0]}},
        "sched": {"class_type": "BasicScheduler",
                  "inputs": {"model": ["L_model", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0}},
        "ksamp": {"class_type": "SamplerCustomAdvanced",
                  "inputs": {"noise": ["noise", 0], "guider": ["guider", 0],
                             "sampler": ["sampler", 0], "sigmas": ["sched", 0], "latent_image": ["R2V", 1]}},
        "vdec": {"class_type": "VAEDecode", "inputs": {"samples": ["ksamp", 0], "vae": ["L_vvae", 0]}},
        "adec": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["ksamp", 0], "vae": ["L_avae", 0]}},
        "mkvid": {"class_type": "CreateVideo", "inputs": {"images": ["vdec", 0], "audio": ["adec", 0], "fps": 24.0}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["mkvid", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }
    # Autogrow 的正確 API 形式:ref_images 是一個 dict(execute 內部跑 .values()),
    # 鍵用 template prefix 的 ref_image_<i>,順序即 <Picture 1..N> 的對應順序
    refs = {}
    for i, n in enumerate(names):
        nid = f"img{i}"
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": n}}
        refs[f"ref_image_{i}"] = [nid, 0]
    g["R2V"]["inputs"]["ref_images"] = refs
    return g


def main():
    pid = sys.argv[1]
    o = {"size": "match", "scene": "kitchen", "seed": "4001", "refs": "char", "out": ""}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    with_char = (o["refs"] == "char")
    sc = o["scene"]
    if sc in SCENES_AHAO:
        scene_img = SCENES_AHAO[sc][0]; refdir = REFS.replace("/refs", "/refs-ahao")
        chars = ["char-ahao-fourview.png", "char-ahao-closeup.png"]
    elif sc in SCENES_YUN:
        scene_img = SCENES_YUN[sc][0]; refdir = REFS.replace("/refs", "/refs-yun")
        chars = ["char-yun-fourview.png", "char-yun-closeup.png"]
    else:
        scene_img = SCENES[sc][0]; refdir = REFS
        chars = ["character-ajen-fourview.png", "character-ajen-closeup.png"]
    files = (chars + [scene_img]) if with_char else []
    out = o["out"] or f"r2v_{o['scene']}_{o['refs']}"
    print(f"場景={o['scene']} 參考={o['refs']} seed={o['seed']} → {out}")
    names = [upload(pid, os.path.join(refdir, f)) for f in files] if files else []
    globals()["PROMPT"] = make_prompt(o["scene"], with_char)
    wf = build(names, o["size"], int(o["seed"]), out)
    r = post_json(base(pid) + "/prompt", {"prompt": wf, "client_id": "r2v-" + uuid.uuid4().hex[:8]})
    pid_job = r.get("prompt_id")
    if not pid_job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:600]); sys.exit(1)
    print(f"SUBMITTED job={pid_job} size={o['size']} seed={o['seed']} {W}x{H}x{FR} steps={STEPS}")
    t0 = time.time()
    while True:
        time.sleep(20)
        os.utime("/tmp/rp-lease-heartbeat", None)          # 續租
        try:
            h = json.load(_get(base(pid) + f"/history/{pid_job}", timeout=60))
        except Exception as e:
            print("  poll err", e); continue
        if pid_job in h:
            st = h[pid_job].get("status", {})
            dt = time.time() - t0
            if st.get("status_str") == "error" or not st.get("completed", True):
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:800]); sys.exit(1)
            outs = h[pid_job].get("outputs", {})
            print(f"DONE in {dt:.0f}s → {json.dumps(outs, ensure_ascii=False)[:400]}")
            return
        el = time.time() - t0
        print(f"  running {el/60:.1f}min")
        if el > 3600: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
