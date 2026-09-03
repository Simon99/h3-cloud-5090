#!/usr/bin/env python3
"""本機 4060 的 LTX-2.5 latent 2× 放大:960×544 → 1920×1088。
用法: ltx_up.py <輸入mp4> [<輸出前綴>]

依據(2026-08-30 實測):LTX 2× = 60s,Real-ESRGAN = 526s(慢 8.8 倍)且有數位光暈與塑膠感。
搭配 H3 在 544P 與 480P 同為 82s 的固定開銷平台期 → 「雲端 544P 生成 + 本機 LTX 放大」
比雲端 736P 直出更快、解析度更高,而且避開了把 ComfyUI 打死的高解析度 VAE 解碼。
"""
import json, os, sys, time, urllib.request, uuid

BASE = "http://127.0.0.1:8189"


def _pick_upscaler():
    """從 enum 自動挑 spatial 放大器——檔名硬編碼已三度因版本後綴踩坑"""
    d = json.load(urllib.request.urlopen(BASE + "/object_info/LatentUpscaleModelLoader", timeout=30))
    spec = d["LatentUpscaleModelLoader"]["input"]["required"]["model_name"]
    # COMBO 兩種格式:舊=[options,cfg]、新=["COMBO",{"options":[...]}]
    opts = spec[1]["options"] if spec[0] == "COMBO" else spec[0]
    for o in opts:
        if "spatial" in o:
            return o
    raise SystemExit("找不到 spatial 放大器")



def submit(path, prefix):
    name = os.path.basename(path)
    g = {
        "lv": {"class_type": "LoadVideo", "inputs": {"file": name}},
        "gc": {"class_type": "GetVideoComponents", "inputs": {"video": ["lv", 0]}},
        "vae": {"class_type": "VAELoader",
                "inputs": {"vae_name": "ltx-2.5-video-vae-conv-bf16.safetensors"}},
        "up": {"class_type": "LatentUpscaleModelLoader",
               "inputs": {"model_name": _pick_upscaler()}},
        "enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["gc", 0], "vae": ["vae", 0]}},
        "ups": {"class_type": "LTXVLatentUpsampler",
                "inputs": {"samples": ["enc", 0], "upscale_model": ["up", 0], "vae": ["vae", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["ups", 0], "vae": ["vae", 0]}},
        "mk": {"class_type": "CreateVideo",
               "inputs": {"images": ["dec", 0], "audio": ["gc", 1], "fps": 24.0}},
        "sv": {"class_type": "SaveVideo",
               "inputs": {"video": ["mk", 0], "filename_prefix": prefix,
                          "format": "mp4", "codec": "h264"}},
    }
    req = urllib.request.Request(BASE + "/prompt",
                                 data=json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    pid = r.get("prompt_id")
    if not pid:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:700]); sys.exit(1)
    return pid


def main():
    src = os.path.abspath(sys.argv[1])
    prefix = sys.argv[2] if len(sys.argv) > 2 else ("up_" + os.path.splitext(os.path.basename(src))[0])
    dst = os.path.expanduser("~/ComfyUI-H3/input/" + os.path.basename(src))
    if os.path.abspath(dst) != src:
        import shutil; shutil.copy2(src, dst)
    job = submit(src, prefix)
    print(f"SUBMITTED {os.path.basename(src)} → {prefix}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(15)
        try:
            h = json.load(urllib.request.urlopen(BASE + f"/history/{job}", timeout=60))
        except Exception:
            continue
        if job in h:
            st = h[job].get("status", {})
            if st.get("status_str") == "error":
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:800]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        if time.time() - t0 > 1200:
            print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
