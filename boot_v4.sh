#!/usr/bin/env bash
# v4 boot: everything is IN this image. First boot reassembles model files from /workspace/parts
# chunks (size-verified), then starts ComfyUI. No network needed for models. Fully self-contained.
# Env: GN>0 run cloud_gen after up;GW/GH/GF/GSTEPS/GTURBO/GSHOTS* pass through to cloud_gen.
set -uo pipefail
t(){ date +%T; }
echo "[$(t)] V4_BOOT"
C=/workspace/ComfyUI; OUT=/root/out; mkdir -p "$OUT" /root/tmp "$C/models/loras"
python - <<'PY'
import json, os, glob
C="/workspace/ComfyUI/models"; P="/workspace/parts"
man=json.load(open("/workspace/h/parts_manifest.json"))
for m in man:
    dst=os.path.join(C, m["path"])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst)==m["size"]:
        print("  have", m["name"], flush=True); continue
    parts=sorted(glob.glob(os.path.join(P, m["name"]+".p*")))
    assert len(parts)==m["chunks"], f"missing chunks for {m['name']}: {len(parts)}/{m['chunks']}"
    print("  assembling", m["name"], f"({m['size']/1e9:.1f}GB, {len(parts)} parts)", flush=True)
    with open(dst,"wb") as o:
        for p in parts:
            with open(p,"rb") as f:
                while True:
                    b=f.read(1<<24)
                    if not b: break
                    o.write(b)
    got=os.path.getsize(dst)
    assert got==m["size"], f"size mismatch {m['name']}: {got}!={m['size']}"
    print("  ok", m["name"], flush=True)
print("ASSEMBLY_DONE", flush=True)
PY
echo "[$(t)] models ready: $(du -sh $C/models 2>/dev/null|cut -f1)"
SAGE=""; python -c "import sageattention" 2>/dev/null && SAGE="--use-sage-attention"
nohup python "$C/main.py" --listen 0.0.0.0 --port 8188 --output-directory "$OUT" --temp-directory /root/tmp $SAGE > /root/comfy.log 2>&1 &
for i in $(seq 1 120); do curl -s -m3 http://127.0.0.1:8188/object_info >/dev/null 2>&1 && { echo "[$(t)] COMFY_UP"; break; }; sleep 3; done
if [ "${GN:-0}" -gt 0 ]; then cd /workspace/h && python3 -u cloud_gen.py; fi
echo "[$(t)] V4_READY"
