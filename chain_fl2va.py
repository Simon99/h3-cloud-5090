#!/usr/bin/env python3
"""FL2VA 關鍵幀鏈:每鏡吃「首幀 + 末幀」,上一鏡的末幀就是下一鏡的首幀 → 整段動作連戲。
用法: chain_fl2va.py <podId> --shot=<name> [--seed=N] [--out=name] [--w= --h=]

為什麼走這條:H3 文生視頻三度拒絕生出騰空動作(每次攤平成地面高踢),
但生圖模型畫「騰空定格」毫無問題 → 把姿態釘進首末幀,模型只能從那裡演。
雲端 v5 映像沒有 H3Keyframes 自訂節點(那是本機的),只有內建 MiniMaxH3ImageToVideo,
故用首末幀;鏡間共用同一張圖當接點,等效於連續動作。
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

KF = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
UNET_FL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
STYLE = ("3D animated feature film, cinematic lighting, professional boxing ring under overhead "
         "arena spotlights, dark blurred arena crowd behind. ")
CAST = ("A slender young Asian woman as a 3D animated character — black bob hair, fitted sleeveless "
        "knee-length red dress, pink silk scarf knotted at her throat, nude heels, red boxing gloves — "
        "spars with a chubby anthropomorphic giant panda standing upright on two legs in a white "
        "taekwondo dobok with a blue belt and red boxing gloves. "
        "EXACTLY ONE woman and EXACTLY ONE panda, never duplicated. ")
TAIL = " No on-screen text, no subtitles, no captions, no logos, no speaking."

# name: (首幀, 末幀 or None, 鏡頭內的動作描述)
SHOTS = {
    "s1_windup_kick":  ("kf_windup.png",    "kf_spinkick.png",
        "She drops low, coils her body, then explodes off the canvas into a flying spinning back kick "
        "that lands against the panda's raised double-arm block. The motion accelerates into the impact."),
    "s2_kick_knock":   ("kf_spinkick.png",  "kf_knockback.png",
        "The block holds and throws her backwards through the air; she lands and skids back across the "
        "canvas, knees bending to absorb it, while the panda stays planted behind his guard."),
    "s3_knock_sweep":  ("kf_knockback.png", "kf_sweep.png",
        "The panda drives forward off his guard, pivots on one foot and whips his other leg out into a "
        "fast low sweeping kick skimming the canvas toward her ankles. She reacts and shifts her weight."),
    "s4_sweep_flip":   ("kf_sweep.png",     "kf_backflip.png",
        "She springs off the ball of one foot and snaps into a backflip, tucking and rotating backwards "
        "as the panda's sweeping leg passes through empty air beneath her."),
    # 末幀用 kf_windup:落地後回到起手戒備式,整段動作首尾相接成一個循環
    # (原本要用的 kf_landing 被生圖端的安全系統連擋三次,沒生出來;改用既有幀反而收得更好)
    "s5_flip_land":    ("kf_backflip.png",  "kf_windup.png",
        "She completes the rotation and drops back down onto her feet, knees flexing to absorb the landing, "
        "then settles into a low ready stance with both gloves raised in front of her, eyes back on the panda, "
        "who pulls his sweeping leg back in and straightens up into his own guard."),
    # 特寫(只給首幀,讓它自然微動)
    "c1_eyes":  ("kf_cu_eyes.png",  None,
        "Slow push-in on her face. Her eyes narrow with focus, a single breath, jaw setting."),
    "c2_guard": ("kf_cu_guard.png", None,
        "Tight on the panda's face and forearms at the moment of impact; his fur ripples with the shock, "
        "his eyes squeeze then reopen, holding firm."),
    "c3_heel":  ("kf_cu_heel.png",  None,
        "Tight low shot on her heels touching down on the canvas, dust puffing out, the shoe flexing, "
        "then pushing off again."),
}


def pick_unet(pid):
    """從 pod 實際的 UNETLoader enum 挑 fl2va 權重——檔名用猜的會在開機後才炸,浪費一次開機"""
    d = json.load(T._get(T.base(pid) + "/object_info/UNETLoader", timeout=90))
    opts = d["UNETLoader"]["input"]["required"]["unet_name"][0]
    for o in opts:
        if "fl2va" in o.lower():
            print(f"  FL2VA 權重: {o}"); return o
    raise SystemExit(f"pod 上沒有 fl2va 權重,現有:{opts}(開 pod 要帶 --set=fl2va 或 both)")


def build(unet, first_name, last_name, prompt, seed, prefix, w, h, fr, steps):
    g = {
        "L_model": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "L_clip": {"class_type": "CLIPLoader",
                   "inputs": {"clip_name": T.CLIP, "type": "minimax"}},
        "L_vvae": {"class_type": "VAELoader", "inputs": {"vae_name": T.VVAE}},
        "I2V": {"class_type": "MiniMaxH3ImageToVideo",
                "inputs": {"clip": ["L_clip", 0], "vae": ["L_vvae", 0], "prompt": prompt,
                           "width": w, "height": h, "length": fr}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "guider": {"class_type": "BasicGuider", "inputs": {"model": ["L_model", 0], "conditioning": ["I2V", 0]}},
        "sched": {"class_type": "BasicScheduler",
                  "inputs": {"model": ["L_model", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "ksamp": {"class_type": "SamplerCustomAdvanced",
                  "inputs": {"noise": ["noise", 0], "guider": ["guider", 0],
                             "sampler": ["sampler", 0], "sigmas": ["sched", 0], "latent_image": ["I2V", 1]}},
        "vdec": {"class_type": "VAEDecode", "inputs": {"samples": ["ksamp", 0], "vae": ["L_vvae", 0]}},
        "mkvid": {"class_type": "CreateVideo", "inputs": {"images": ["vdec", 0], "fps": 24.0}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["mkvid", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }
    g["F"] = {"class_type": "LoadImage", "inputs": {"image": first_name}}
    g["I2V"]["inputs"]["first_frame"] = ["F", 0]
    if last_name:
        g["L"] = {"class_type": "LoadImage", "inputs": {"image": last_name}}
        g["I2V"]["inputs"]["last_frame"] = ["L", 0]
    return g


def main():
    pid = sys.argv[1]
    o = {"shot": "s1_windup_kick", "seed": "8101", "out": "", "w": "", "h": "", "fr": "141", "steps": "20"}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    first, last, motion = SHOTS[o["shot"]]
    out = o["out"] or o["shot"]
    files = [first] + ([last] if last else [])
    print(f"FL2VA {o['shot']}  首幀={first}  末幀={last or '(無)'}  seed={o['seed']} → {out}")
    unet = pick_unet(pid)
    names = [T.upload(pid, os.path.join(KF, f)) for f in files]
    prompt = STYLE + CAST + motion + TAIL
    wf = build(unet, names[0], (names[1] if last else None), prompt, int(o["seed"]), out,
               int(o["w"] or 960), int(o["h"] or 544), int(o["fr"]), int(o["steps"]))
    r = T.post_json(T.base(pid) + "/prompt", {"prompt": wf, "client_id": "fl-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:700]); sys.exit(1)
    print(f"SUBMITTED job={job}", flush=True)
    t0 = time.time(); miss = 0
    while True:
        time.sleep(20)
        try: os.utime("/tmp/rp-lease-heartbeat", None)
        except Exception: pass
        try:
            h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60))
            miss = 0
        except Exception as e:
            miss += 1
            print(f"  poll err({miss}) {e}")
            # 教訓(2026-08-31):1312x736x141 的 VAE 解碼把 ComfyUI 打死,映像無 sshd 無法重啟。
            # 傻等 40 分鐘 timeout 只是燒錢,後面每一鏡還會再撞同一面牆 → 探活後快速失敗。
            if miss >= 6:
                try:
                    json.load(T._get(T.base(pid) + "/queue", timeout=45)); miss = 0
                except Exception:
                    print("COMFY_DEAD ComfyUI 已無回應——中止本鏡與整批"); sys.exit(2)
            continue
        if job in h:
            st = h[job].get("status", {})
            if st.get("status_str") == "error":
                print("RUN_ERR", json.dumps(st, ensure_ascii=False)[:900]); sys.exit(1)
            print(f"DONE in {time.time()-t0:.0f}s"); return
        el = time.time() - t0
        print(f"  running {el/60:.1f}min", flush=True)
        if el > 2400: print("TIMEOUT"); sys.exit(1)


if __name__ == "__main__":
    main()
