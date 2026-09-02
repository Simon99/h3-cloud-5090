#!/usr/bin/env python3
"""TRT-VAE 品質驗證:一次真實 REF2VA 生成,同一顆 latent 分別走標準 VAE 與 TRT VAE 解碼,
輸出兩支影片逐幀對比。用法: probe_trtq.py <podId> [--seed=N]"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

PT = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
IMGS = [f"{PT}/char-qipao-fourview.png", f"{PT}/char-qipao-closeup.png", f"{PT}/scene-boxing-ring.png"]
PROMPT = ("Photorealistic live-action film still. The woman shown in <Picture 1> and <Picture 2> — a young "
          "Chinese woman in a mini-length deep-red gold-embroidered silk qipao — practices slow martial-arts "
          "forms alone in the boxing ring shown in <Picture 3>, warm and cool arena lighting, hazy air. "
          "EXACTLY ONE woman. No on-screen text, no logos, no speech.")


def main():
    pid = sys.argv[1]
    o = {"seed": "9901"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    # 先編引擎
    g = {"c": {"class_type": "MiniMaxH3TRTCompilerNode",
               "inputs": {"decoder_onnx": "minimax_h3_vae_decoder.onnx",
                          "encoder_onnx": "minimax_h3_vae_encoder.onnx",
                          "delete_onnx_after_compile": False}}}
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "q-" + uuid.uuid4().hex[:8]})
    job = r["prompt_id"]; t0 = time.time()
    while True:
        time.sleep(10)
        h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60))
        if job in h:
            st = h[job].get("status", {})
            if st.get("status_str") == "error":
                print("COMPILE_ERR", json.dumps(st)[:400]); sys.exit(1)
            print(f"COMPILED {time.time()-t0:.0f}s"); break
    # 真實生成 + 雙解碼
    T.PROMPT = PROMPT
    names = [T.upload(pid, f) for f in IMGS]
    wf = T.build(names, "match", int(o["seed"]), "trtq_std", w=960, h=544)
    wf["trtv"] = {"class_type": "MiniMaxH3TRTVAELoader",
                  "inputs": {"decoder": "minimax_h3_vae_decoder.engine",
                             "encoder": "minimax_h3_vae_encoder.engine"}}
    wf["vdec2"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ksamp", 0], "vae": ["trtv", 0]}}
    wf["mkvid2"] = {"class_type": "CreateVideo", "inputs": {"images": ["vdec2", 0], "audio": ["adec", 0], "fps": 24.0}}
    wf["save2"] = {"class_type": "SaveVideo",
                   "inputs": {"video": ["mkvid2", 0], "filename_prefix": "trtq_trt", "format": "mp4", "codec": "h264"}}
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": wf, "client_id": "q-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job: print("SUBMIT_ERR", json.dumps(r)[:600]); sys.exit(1)
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
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:800]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        print(f"  running {(time.time()-t0)/60:.1f}min", flush=True)
        if time.time() - t0 > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
