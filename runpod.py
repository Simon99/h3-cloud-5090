#!/usr/bin/env python3
"""RunPod adapter — 與 Vast 同一套 gate/驗屍哲學,事件記進 pod_stats.jsonl(provider=runpod)。
用法:
  runpod.py balance
  runpod.py create <gpu> [--set ref2va|fl2va|both] [--gn N] [--disk 140] [--name X]
  runpod.py status <podId>
  runpod.py url <podId>            # ComfyUI proxy URL
  runpod.py kill <podId>           # 驗屍式終止
  runpod.py list
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

API = "https://api.runpod.io/graphql"
DIR = os.path.dirname(os.path.abspath(__file__))


def key():
    return open(os.path.expanduser("~/.runpod-key")).read().strip()


def gql(query, timeout=60):
    req = urllib.request.Request(API, data=json.dumps({"query": query}).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                                          "Authorization": "Bearer " + key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    if d.get("errors"):
        raise SystemExit("GQL_ERR: " + json.dumps(d["errors"], ensure_ascii=False)[:500])
    return d["data"]


def log_event(**kv):
    subprocess.run([sys.executable, os.path.join(DIR, "pod_stats.py"), "log", kv.pop("event")]
                   + [f"{k}={v}" for k, v in kv.items()], capture_output=True)


def balance(_):
    m = gql("query { myself { clientBalance currentSpendPerHr } }")["myself"]
    print(f"餘額 ${m['clientBalance']:.2f}  目前時薪支出 ${m.get('currentSpendPerHr') or 0:.3f}")
    return m["clientBalance"]


REST = "https://rest.runpod.io/v1"


def rest(method, path, body=None, timeout=120):
    req = urllib.request.Request(REST + path, method=method,
                                 data=(json.dumps(body).encode() if body is not None else None),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                                          "Authorization": "Bearer " + key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"REST {method} {path} → {e.code}: {e.read().decode()[:400]}")


# 開機期進度必須可觀測:8189 靜態服務 /root + 每 20 秒寫 progress.txt(時間戳 已下載bytes log大小)
BOOTCMD = (
    "python3 -m http.server 8189 --directory /root >/dev/null 2>&1 & "
    "(while true; do echo $(date +%s) "
    "$(du -sb /workspace/ComfyUI/models 2>/dev/null | cut -f1) "
    "$(stat -c %s /root/comfy.log 2>/dev/null || echo 0) > /root/progress.txt; sleep 20; done) & "
    "bash /workspace/h/boot_v5.sh > /root/boot.log 2>&1; tail -f /dev/null"
)

# 額外權重(如 turbo LoRA):開機時一併抓,因為映像無 sshd、事後無法送檔進去
EXTRA = {
  "heretic_te": ("text_encoders", "qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors",
    "https://huggingface.co/Momoking/Qwen3-VL-32B-Heretic-MiniMax-H3-NVFP4/resolve/main/"
    "qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors"),
  "ref2v_turbo": ("loras", "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
    "https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/"
    "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"),
}


def create(argv):
    # 位置參數才是 GPU 名;--flag 一律進 o(否則 `create --cloud=X` 會把旗標當成 GPU 型號)
    gpu = argv[0] if argv and not argv[0].startswith("--") else "NVIDIA GeForce RTX 5090"
    o = {"set": "fl2va", "gn": "0", "disk": "140", "name": "h3-canary"}
    for a in argv:
        if a.startswith("--"):
            k, _, v = a[2:].partition("="); o[k] = v
    hft = open(os.path.expanduser("~/.hf-token")).read().strip()
    bootcmd = BOOTCMD
    pre = ""
    for k in (o.get("extra") or "").split("+"):
        if k in EXTRA:
            sub, fn, url = EXTRA[k]
            pre += (f"mkdir -p /workspace/ComfyUI/models/{sub} && "
                    f"(curl -L --retry 5 -C - -s '{url}' "
                    f"-o /workspace/ComfyUI/models/{sub}/{fn} && echo EXTRA_OK_{k} >> /root/boot.log) & ")
    if o.get("precmd"):
        # 前置序列指令(pip install 等,需在 ComfyUI 啟動前完成——不用 & 背景)
        pre += o["precmd"].rstrip(";") + " ; "
    if pre:
        bootcmd = pre + BOOTCMD
    body = {
        "name": o["name"], "imageName": o.get("image", "kyrox/h3-gen:v5"),
        "gpuTypeIds": [gpu], "gpuCount": 1, "cloudType": o.get("cloud", "SECURE"),
        "containerDiskInGb": int(o["disk"]), "volumeInGb": 0,
        "ports": ["8188/http", "8189/http", "22/tcp"],
        "env": {"HF_TOKEN": hft, "MODEL_SET": o["set"], "GN": o["gn"],
                **({"PUBLIC_KEY": open(os.path.expanduser("~/.ssh/id_rsa.pub")).read().strip()}
                   if o.get("plain") == "1" else {})},
        # vastai 基底映像自帶 entrypoint 會吞掉 CMD → 必須覆寫 entrypoint 才跑得到我們的啟動腳本
        # --plain=1:用官方映像的預設啟動(sshd 等),不覆寫 entrypoint,env 帶 PUBLIC_KEY
        **({} if o.get("plain") == "1" else
           {"dockerEntrypoint": ["/bin/bash", "-c", bootcmd], "dockerStartCmd": []}),
        "minDownloadMbps": 500,          # 租前 gate:頻寬太差的不要
        "minDiskBandwidthMBps": 400,
    }
    try: os.remove("/tmp/runpod-pod.txt")
    except FileNotFoundError: pass
    bl = set()
    blf = os.path.join(DIR, "host_blacklist.txt")
    if os.path.exists(blf):
        for ln in open(blf):
            ln = ln.strip()
            if ln.startswith("runpod:"): bl.add(ln.split(":", 1)[1])
    for attempt in range(4):
        d = rest("POST", "/pods", body)
        pid = d.get("id")
        if not pid: raise SystemExit("建立失敗:" + json.dumps(d)[:300])
        mid = d.get("machineId")
        if mid in bl:
            print(f"  ✗ 落到黑名單機器 {mid},銷毀重租({attempt+1}/4)")
            kill([pid]); time.sleep(3)
            continue
        break
    else:
        raise SystemExit("連續 4 次落到黑名單機器,放棄")
    print(f"pod {pid}  machine {d.get('machineId')}  ${d.get('costPerHr')}/hr")
    log_event(event="rented", provider="runpod", pod=pid, machine=d.get("machineId"), dph=d.get("costPerHr"))
    open("/tmp/runpod-pod.txt", "w").write(pid + "\n")
    return pid


def _pod(pid):
    q = ('query { pod(input: {podId: "%s"}) { id desiredStatus costPerHr '
         'runtime { uptimeInSeconds ports { ip isIpPublic privatePort publicPort type } } } }' % pid)
    return gql(q)["pod"]


def status(argv):
    p = _pod(argv[0])
    rt = p.get("runtime") or {}
    print(f"{p['id']}  {p['desiredStatus']}  ${p['costPerHr']}/hr  up={rt.get('uptimeInSeconds', 0)}s")
    for x in (rt.get("ports") or []):
        print(f"  {x['privatePort']}/{x['type']} → {x['ip']}:{x['publicPort']} public={x['isIpPublic']}")
    return p


def url(argv):
    print(f"https://{argv[0]}-8188.proxy.runpod.net")


def kill(argv):
    pid = argv[0]
    for t in range(3):
        gql('mutation { podTerminate(input: {podId: "%s"}) }' % pid)
        time.sleep(5)
        pods = gql("query { myself { pods { id } } }")["myself"]["pods"]
        if not any(p["id"] == pid for p in pods):
            print(f"terminated+verified {pid}")
            log_event(event="destroyed", provider="runpod", pod=pid)
            # 走 kill 路徑也要清掉 warden 租約,否則留下指向不存在 pod 的幽靈租約
            _lp = os.path.expanduser(f"~/.runpod-warden/leases/{pid}.json")
            if os.path.exists(_lp):
                os.remove(_lp); print(f"  已清除 warden 租約 {pid}")
            return
        print(f"terminate 未生效,重試 {t+1}")
    print(f"WARN {pid} 未確認終止,需人工")


def reconcile(_):
    """對帳:把仍無 destroyed 記錄、但帳上已不存在的 pod 補記(warden release/擊殺不會寫我們的 log)"""
    import time as _t
    live = {p["id"] for p in gql("query { myself { pods { id } } }")["myself"]["pods"]}
    db = os.path.join(DIR, "pod_stats.jsonl")
    rows = [json.loads(l) for l in open(db) if l.strip()]
    opened, closed = {}, set()
    for r in rows:
        if r.get("provider") != "runpod": continue
        if r["event"] == "rented": opened[r.get("pod")] = r
        elif r["event"] in ("destroyed", "gate_kill"): closed.add(r.get("pod"))
    orphan = [p for p in opened if p not in closed and p not in live]
    for p in orphan:
        log_event(event="destroyed", provider="runpod", pod=p, note="reconciled_warden")
        print(f"  補記 destroyed: {p}")
    print(f"對帳完成:已補 {len(orphan)} 筆;帳上仍存活 {len(live)} 台")


def lst(_):
    m = gql("query { myself { pods { id name desiredStatus costPerHr } networkVolumes { id name size } } }")["myself"]
    print("pods:", [(p["id"], p["name"], p["desiredStatus"], p["costPerHr"]) for p in (m.get("pods") or [])])
    print("volumes:", [(v["id"], v["name"], v["size"]) for v in (m.get("networkVolumes") or [])])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balance"
    {"balance": balance, "create": create, "status": status, "url": url,
     "kill": kill, "list": lst, "reconcile": reconcile}[cmd](sys.argv[2:])
