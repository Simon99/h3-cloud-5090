#!/usr/bin/env python3
"""FL2V Turbo canary:chain_fl2va 圖 + 可選 LoRA(lightx2v 官方蒸餾)。
用法: fl2v_turbo.py <podId> --shot=w2_kick --steps=4 [--lora=<檔名|none>] [--w= --h=] [--seed=] [--out=]
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T
import chain_fl2va as CF


def main():
    pid = sys.argv[1]
    o = {"shot": "w2_kick", "seed": "8101", "out": "", "w": "960", "h": "544",
         "fr": "141", "steps": "20", "lora": "none"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    first, last, motion = CF.SHOTS2[o["shot"]]
    out = o["out"] or o["shot"]
    unet = CF.pick_unet(pid)
    names = [T.upload(pid, os.path.join(CF.KF, f)) for f in (first, last)]
    prompt = CF.STYLE2 + CF.CAST2 + motion + CF.TAIL
    g = CF.build(unet, names[0], names[1], prompt, int(o["seed"]), out,
                 int(o["w"]), int(o["h"]), int(o["fr"]), int(o["steps"]))
    if o["lora"] != "none":
        g["lora"] = {"class_type": "LoraLoaderModelOnly",
                     "inputs": {"model": ["L_model", 0], "lora_name": o["lora"], "strength_model": 1.0}}
        g["guider"]["inputs"]["model"] = ["lora", 0]
        g["sched"]["inputs"]["model"] = ["lora", 0]
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": g, "client_id": "ft-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job or r.get("node_errors"):
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:1200]); sys.exit(1)
    print(f"SUBMITTED steps={o['steps']} lora={o['lora']}", flush=True)
    t0 = time.time(); miss = 0
    while True:
        time.sleep(15)
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
        if time.time() - t0 > 1800: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
