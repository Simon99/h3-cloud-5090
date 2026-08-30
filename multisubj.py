#!/usr/bin/env python3
"""多主體 REF2VA 測試:一鏡放 2-3 個已建好參考的角色,檢驗 H3 能否同時鎖住多個身份。
用法: multisubj.py <podId> --case=duo|trio --seed=N [--out=name] [--w= --h=]

參考圖插入順序即 <Picture N> 順序(Autogrow dict),prompt 明確把每個人綁到自己的圖號。
"""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turbo_ab as T

NM = os.path.expanduser("~/claude-sandboxes/director/research/experiments/nightmarket-consistency")

AJEN = ("a Taiwanese street-food vendor in her forties, round face, navy headscarf over a low bun, "
        "white short-sleeve polo, faded indigo denim bib apron, pale green jade bangle, small gold earrings")
AHAO = ("a muscular Taiwanese vendor in his early thirties, buzz-cut hair under a black sweatband, "
        "square jaw with short stubble, white fitted sleeveless tank top, dark grey waist-tied apron, "
        "a Japanese wave tattoo down his left forearm, white towel around his neck")
YUN = ("a young Taiwanese craftswoman in her early twenties, long straight black hair loosely tied back, "
       "round wire-frame glasses, oversized cream knitted cardigan over a plain tee, no makeup")

PT = os.path.expanduser("~/claude-sandboxes/director/research/experiments/panda-taekwondo/refs")
LADY = ("a slender young Asian woman in her twenties, long straight black hair past her shoulders, "
        "a fitted sleeveless red cocktail dress, a soft pink silk scarf knotted at her throat, "
        "natural light makeup")
PANDA = ("a chubby anthropomorphic giant panda standing upright on two legs, rounded belly, "
         "classic black-and-white markings with black eye patches and black ears, "
         "a white taekwondo dobok with a blue belt tied at the waist, barefoot, friendly face")
BOX_REFS = [f"{PT}/char-lady-fourview.png", f"{PT}/char-lady-closeup.png",
            f"{PT}/char-panda-fourview.png", f"{PT}/char-panda-closeup.png",
            f"{PT}/scene-boxing-ring.png"]
BOX_BASE = (
    "Cinematic film still, dramatic overhead arena spotlights, hazy atmosphere, shallow depth of field. "
    f"A sparring match inside the boxing ring shown in <Picture 5>. "
    f"One fighter is the woman shown in <Picture 1> and <Picture 2> — {LADY} — wearing red boxing gloves. "
    f"The other fighter is the panda shown in <Picture 3> and <Picture 4> — {PANDA} — wearing red boxing gloves. "
    "Her red dress is fitted and knee-length; the pink scarf stays knotted at her throat. "
    "The panda is a person-sized cartoon character who stands upright on two legs like a human, "
    "as tall as the woman, wearing his white dobok top and blue belt. He is NEVER on all fours, "
    "never crawling, never posed like a real four-legged bear. "
    "EXACTLY ONE woman and EXACTLY ONE panda are present — there is only one of each character "
    "in the entire frame, never duplicated. Both are fully visible in the same frame. ")
BOX_TAIL = " No on-screen text, no subtitles, no captions, no logos, no speaking."

BOX_SHOTS = {
    # 名稱: 這一鏡的機位與動作
    "wide":  "Wide establishing shot at eye level from outside the ropes, both fighters full-body in the "
             "centre of the canvas, circling each other with guards raised. Slow push-in.",
    "low":   "Low angle shot from the canvas looking up, the panda launching a high roundhouse kick while "
             "the woman ducks under it, the overhead lights flaring behind them. Camera static.",
    "ots":   "Over-the-shoulder shot from behind the woman's right shoulder, her shoulder and pink scarf "
             "soft in the foreground, the panda sharp in the background throwing a straight punch toward camera.",
    "close": "Tight two-shot at chest height, the two fighters locked close together in a clinch, gloves "
             "pressed against each other, breathing hard, faces clearly visible. Slow drift to the left.",
    "high":  "High angle shot looking down on the ring from above the corner post, both fighters small in "
             "frame against the blue canvas, the panda advancing as the woman backs toward the ropes.",
    # ——— 編排段落:四拍連續動作,每拍配一個機位 ———
    "c1_spinkick":
        "Low side angle, wide enough to hold both full bodies. The woman leaps off the canvas into a "
        "flying spinning back kick, her body turning horizontally in mid-air, one leg extended straight "
        "toward the panda's head, her red dress and pink scarf trailing with the spin. The panda plants "
        "his feet and snaps both forearms up in front of his face into a tight double-arm block. "
        "Motion blur on the kicking leg, dust and haze kicked up in the spotlight beam.",
    "c2_knockback":
        "Medium shot at chest height from the side. The instant of impact: the woman's shin slams into the "
        "panda's crossed forearms, the block holds, and the force throws her backwards through the air. "
        "She is driven back and away, arms flung out for balance, hair and scarf whipping forward. "
        "The panda stays planted and unmoved behind the block.",
    "c3_sweep":
        "Very low angle, camera almost at canvas level looking along the floor. The panda charges forward "
        "to where the woman has landed, drops low onto one hand and sweeps his other leg in a wide low "
        "sweeping kick across the canvas toward her ankles, his blue belt swinging out with the turn.",
    "c4_backflip":
        "Wide side-on shot holding both fighters. The woman touches down on the ball of one foot and "
        "immediately springs into a backflip, tucking and rotating backwards over the incoming sweep, "
        "the panda's sweeping leg passing through empty air beneath her. She is upside down at the apex "
        "of the flip, red dress and scarf hanging with the rotation.",
    # ——— 重擲版 ———
    "r1_spinkick":
        "Low side angle from outside the ropes, wide enough to hold both full bodies. The woman jumps "
        "high with BOTH FEET COMPLETELY OFF THE CANVAS, her whole body spinning a full turn horizontally "
        "in mid-air, and whips her rear leg around into a spinning back kick aimed at the panda's head. "
        "She is airborne at the peak of the spin, nothing touching the ground. The panda plants his feet "
        "and snaps both forearms up in front of his face into a tight double-arm block.",
    "r3_sweep":
        "Low angle from knee height at the side of the ring, both fighters full-body in frame. The panda "
        "charges forward, drops into a deep crouch with one palm on the canvas, and swings his other leg "
        "in a fast wide circular sweep along the floor toward the woman's ankles, his blue belt flying out "
        "with the turn. The sweeping leg is fully extended and skimming the canvas.",
    "r4_backflip":
        "Wide side-on shot at chest height holding both fighters with clear space between them. The woman "
        "pushes off the ball of one foot and springs into a full backflip, tucked and rotating backwards "
        "in the air, while the panda's sweeping leg passes through empty space beneath her. She is inverted "
        "at the apex of the flip. The panda stays low in his sweep on the canvas.",
    # ——— 第三輪:改寫動作語言 ———
    "s1_flykick":
        "Side view, wide. Freeze the peak of a flying spinning back kick: the woman is AIRBORNE, both of "
        "her feet high off the canvas, her body turned almost horizontal in mid-air after spinning a full "
        "turn, one leg snapped straight out at the panda's head height. Nothing of her touches the ground — "
        "she is completely in the air, hair and skirt lifted by the spin, heavy motion blur. The panda "
        "stands his ground and brings both forearms up in front of his face to block.",
    "s3_lowsweep":
        "Side view, camera at waist height, both fighters standing and full-body in frame. The panda stays "
        "UPRIGHT AND BALANCED ON ONE LEG and whips his other leg out straight in a fast horizontal arc at "
        "ankle height, skimming just above the canvas toward the woman's feet — a low sweeping kick. "
        "His torso stays tall and vertical throughout, arms out for balance, blue belt flying with the turn.",
}

CASES = {
    # name: (檔案清單, prompt)
    "duo": (
        [(f"{NM}/refs/character-ajen-fourview.png"),
         (f"{NM}/refs/character-ajen-closeup.png"),
         (f"{NM}/refs-ahao/char-ahao-fourview.png"),
         (f"{NM}/refs-ahao/char-ahao-closeup.png"),
         (f"{NM}/refs-ahao/scene-mianxian-night.png")],
        "Photorealistic documentary cinematography, night market at dusk, mixed neon and warm stall light. "
        f"TWO people stand side by side behind the food stall shown in <Picture 5>. "
        f"On the LEFT stands the woman shown in <Picture 1> and <Picture 2> — {AJEN}. "
        f"On the RIGHT stands the man shown in <Picture 3> and <Picture 4> — {AHAO}. "
        "Both face the camera; the woman wipes her hands on her apron while the man stirs a steaming pot. "
        "Both people are fully visible in frame at the same time, medium wide shot, steam drifting between them. "
        "Slow gentle push-in. No people speaking, no on-screen text, no subtitles."),
    "trio": (
        [(f"{NM}/refs/character-ajen-fourview.png"),
         (f"{NM}/refs/character-ajen-closeup.png"),
         (f"{NM}/refs-ahao/char-ahao-fourview.png"),
         (f"{NM}/refs-ahao/char-ahao-closeup.png"),
         (f"{NM}/refs-yun/char-yun-fourview.png"),
         (f"{NM}/refs-yun/char-yun-closeup.png"),
         (f"{NM}/refs-yun/scene-craft-market.png")],
        "Photorealistic documentary cinematography, outdoor craft market in soft afternoon light. "
        f"THREE people stand in a row at the market shown in <Picture 7>. "
        f"On the LEFT stands the woman shown in <Picture 1> and <Picture 2> — {AJEN}. "
        f"In the MIDDLE stands the man shown in <Picture 3> and <Picture 4> — {AHAO}. "
        f"On the RIGHT stands the young woman shown in <Picture 5> and <Picture 6> — {YUN}. "
        "All three face the camera and are fully visible in the same frame, wide shot, natural interaction. "
        "Slow gentle push-in. No people speaking, no on-screen text, no subtitles."),
}


def main():
    pid = sys.argv[1]
    o = {"case": "duo", "seed": "4001", "out": "", "w": "", "h": ""}
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    if o["case"].startswith("box_"):
        files, prompt = BOX_REFS, BOX_BASE + BOX_SHOTS[o["case"][4:]] + BOX_TAIL
    else:
        files, prompt = CASES[o["case"]]
    out = o["out"] or f"ms_{o['case']}_{o['seed']}"
    print(f"多主體 case={o['case']} 參考圖={len(files)} 張 seed={o['seed']} → {out}")
    names = [T.upload(pid, f) for f in files]
    T.PROMPT = prompt
    wf = T.build(names, "match", int(o["seed"]), out,
                 w=(int(o["w"]) if o["w"] else None), h=(int(o["h"]) if o["h"] else None))
    r = T.post_json(T.base(pid) + "/prompt",
                    {"prompt": wf, "client_id": "ms-" + uuid.uuid4().hex[:8]})
    job = r.get("prompt_id")
    if not job:
        print("SUBMIT_ERR", json.dumps(r, ensure_ascii=False)[:600]); sys.exit(1)
    print(f"SUBMITTED job={job}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(20)
        try: os.utime("/tmp/rp-lease-heartbeat", None)
        except Exception: pass
        try:
            h = json.load(T._get(T.base(pid) + f"/history/{job}", timeout=60))
        except Exception as e:
            print("  poll err", e); continue
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
