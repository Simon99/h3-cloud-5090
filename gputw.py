#!/usr/bin/env python3
"""GPUtw.ai client — 台灣本土 GPU 雲(REST API,支援自訂 Docker image)。
與 pod_stats.py 同一套「行情記錄 + 租機 gate」哲學,事件寫進同一個 pod_stats.jsonl(provider=gputw)。

用法:
  gputw.py catalog                # 免認證:GPU 型號/價格/庫存狀態
  gputw.py market                 # 記一筆 gputw 行情到 pod_stats.jsonl
  gputw.py nodes [GPU_NAME]       # 需 key:實際可租節點
  gputw.py create NODE_ID         # 需 key:用 v5 映像開一台(env 由 --env 帶)
  gputw.py status INSTANCE_ID     # 需 key
  gputw.py stop INSTANCE_ID       # 需 key(必驗屍)

API key 放 ~/.gputw-key(或環境變數 GPUTW_API_KEY)。
"""
import json, os, subprocess, sys, urllib.request

BASE = "https://gputw.ai/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pod_stats.jsonl")
IMAGE = "kyrox/h3-gen:v5"


def key():
    k = os.environ.get("GPUTW_API_KEY")
    if k: return k.strip()
    p = os.path.expanduser("~/.gputw-key")
    return open(p).read().strip() if os.path.exists(p) else None


def api(path, body=None, auth=True):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Content-Type": "application/json"})
    if auth:
        k = key()
        if not k: raise SystemExit("需要 API key:寫進 ~/.gputw-key 或設 GPUTW_API_KEY")
        req.add_header("Authorization", "Bearer " + k)
    data = json.dumps(body).encode() if body is not None else None
    if data: req.data = data
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def log_event(**kv):
    subprocess.run([sys.executable, os.path.join(os.path.dirname(DB), "pod_stats.py"), "log",
                    kv.pop("event")] + [f"{k}={v}" for k, v in kv.items()],
                   capture_output=True)


def eff_price(g, cores=8, disk_gb=80):
    """真實時薪 = GPU + CPU核 + 磁碟(gputw 分項計價,Vast 是全包價,要換算才可比)"""
    return g["hourlyPrice"] + cores * g.get("cpuPerCoreHr", 0) + disk_gb * g.get("diskPerGbHr", 0)


def catalog(_=None):
    d = api("/gpus/active", auth=False)["data"]
    print(f"{'GPU':28s} {'VRAM':>5s} {'基礎$/hr':>9s} {'實效*':>7s} {'現貨價':>7s} {'vs Vast':>8s}  狀態")
    for g in d:
        live = g.get("liveRentablePrice"); va = g.get("vastAiPrice")
        ls = f"{live:.3f}" if live else "-"
        vs = f"{va:.3f}" if va else "-"
        print(f"{g['name'][:28]:28s} {g['vramGb']:4d}G {g['hourlyPrice']:9.3f} {eff_price(g):7.3f} "
              f"{ls:>7s} {vs:>8s}  {g['demandStatus']}")
    print("\n* 實效 = GPU + 8 核 CPU + 80GB 磁碟(與 Vast 全包價可比的口徑)")
    return d


def market(_=None):
    d = api("/gpus/active", auth=False)["data"]
    for g in d:
        if "5090" not in g["name"]: continue
        live = g.get("liveRentablePrice")
        log_event(event="market", provider="gputw", gpu="RTX_5090",
                  base=g["hourlyPrice"], eff=round(eff_price(g), 3),
                  live=(round(live, 3) if live else -1), status=g["demandStatus"])
        print(f"logged gputw market: base=${g['hourlyPrice']} eff=${eff_price(g):.3f} "
              f"live={live} status={g['demandStatus']}")


def nodes(argv):
    d = api("/gpus/active", auth=False)["data"]
    want = (argv[0] if argv else "5090").lower()
    for g in d:
        if want not in g["name"].lower(): continue
        r = api(f"/nodes/available?catalogId={g['id']}")
        print(f"=== {g['name']}"); print(json.dumps(r.get("data"), ensure_ascii=False, indent=1)[:2000])


def create(argv):
    node = argv[0]
    env = {}
    for a in argv[1:]:
        if a.startswith("--env="):
            k, _, v = a[6:].partition("="); env[k] = v
    body = {"nodeId": node, "customImage": IMAGE, "sshEnabled": True,
            "bandwidthMbps": 1000, "env": env or None}
    body = {k: v for k, v in body.items() if v is not None}
    r = api("/instances/create", body)
    print(json.dumps(r, ensure_ascii=False)[:1200])
    iid = (r.get("data") or {}).get("instanceId")
    if iid: log_event(event="rented", provider="gputw", pod=iid, node=node)


def status(argv):
    print(json.dumps(api(f"/instances/{argv[0]}"), ensure_ascii=False, indent=1)[:1500])


def stop(argv):
    iid = argv[0]
    print(json.dumps(api("/instances/stop", {"instanceId": iid}), ensure_ascii=False)[:600])
    log_event(event="destroyed", provider="gputw", pod=iid)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "catalog"
    {"catalog": catalog, "market": market, "nodes": nodes,
     "create": create, "status": status, "stop": stop}[cmd](sys.argv[2:])
