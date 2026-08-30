#!/usr/bin/env python3
"""Pod 生命週期統計庫(JSONL)。gate 門檻依時段統計微調的資料基礎。
用法:
  pod_stats.py log <event> pod=47xx [k=v ...]     # 記一筆(自動補 ts/utc_hour)
  pod_stats.py report                              # 分時段彙總
  pod_stats.py suggest                             # 由分位數建議 gate 門檻
events: rented running cuda_ok dispatch dl_probe shot_start chain_done gate_kill destroyed
慣例欄位: pod offer machine geo dph disk_bw inet_down min(距租/距派分鐘) gb rate reason secs chain cost run_tag
"""
import json, os, sys, time
from collections import defaultdict

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pod_stats.jsonl")

def log(argv):
    rec = {"ts": round(time.time(), 1), "utc_hour": time.gmtime().tm_hour, "event": argv[0]}
    for kv in argv[1:]:
        k, _, v = kv.partition("=")
        try: rec[k] = float(v) if "." in v else int(v)
        except ValueError: rec[k] = v
    with open(DB, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("logged", rec["event"], rec.get("pod", ""))

def rows():
    if not os.path.exists(DB): return []
    return [json.loads(l) for l in open(DB) if l.strip()]

def bucket(h):  # 4 小時一檔(UTC)
    return f"UTC{h//4*4:02d}-{h//4*4+3:02d}"

def pct(xs, p):
    if not xs: return None
    xs = sorted(xs); i = min(len(xs)-1, int(round(p/100*(len(xs)-1))))
    return xs[i]

def report(_):
    rs = rows()
    if not rs: print("(empty)"); return
    by = defaultdict(lambda: defaultdict(list))
    kills = defaultdict(list); rents = defaultdict(int)
    for r in rs:
        b = bucket(r["utc_hour"]); e = r["event"]
        if e == "rented": rents[b] += 1
        if e == "running" and "min" in r: by[b]["time_to_running"].append(r["min"])
        if e == "dl_probe" and "rate" in r: by[b]["dl_gb_per_min"].append(r["rate"])
        if e == "shot_start" and "min" in r: by[b]["dispatch_to_start"].append(r["min"])
        if e == "chain_done" and "secs" in r: by[b]["chain_secs"].append(r["secs"])
        if e == "gate_kill": kills[b].append((r.get("reason","?"), r.get("cost", 0)))
    for b in sorted(set(list(by)+list(kills)+list(rents))):
        print(f"\n== {b} (租{rents.get(b,0)}台, 殺{len(kills.get(b,[]))}台, 浪費${sum(c for _,c in kills.get(b,[])):.2f}) ==")
        for m, xs in sorted(by[b].items()):
            print(f"  {m:20s} n={len(xs):3d} P50={pct(xs,50):.1f} P90={pct(xs,90):.1f} max={max(xs):.1f}")
        for reason, cost in kills.get(b, []): print(f"  kill: {reason} (${cost:.2f})")

def suggest(_):
    rs = rows()
    ttr = [r["min"] for r in rs if r["event"]=="running" and "min" in r]
    dl  = [r["rate"] for r in rs if r["event"]=="dl_probe" and "rate" in r]
    cs  = [r["secs"] for r in rs if r["event"]=="chain_done" and "secs" in r]
    print("建議門檻(P90×1.3 buffer;樣本不足 8 筆先沿用現值):")
    if len(ttr) >= 8: print(f"  Gate A 拉映像: {pct(ttr,90)*1.3:.0f} 分 (n={len(ttr)}, P90={pct(ttr,90):.1f})")
    else: print(f"  Gate A: 樣本 {len(ttr)} 筆,沿用 8 分")
    if len(dl) >= 8: print(f"  Gate C 下載率: ≥{max(0.5, pct(dl,10)*0.5):.1f} GB/分 (P10={pct(dl,10):.1f})")
    else: print(f"  Gate C: 樣本 {len(dl)} 筆,沿用 1GB/分(4分3GB)")
    if len(cs) >= 8: print(f"  Gate D 鏈節奏: {pct(cs,90)*1.3/60:.0f} 分/鏈 (P90={pct(cs,90):.0f}s)")
    else: print(f"  Gate D: 樣本 {len(cs)} 筆,沿用 15 分首鏈")

def hosts(_):
    """機器信譽表:依 machine= 欄位彙總 chain_done/gate_kill → 白/黑名單候選"""
    rs = rows()
    from collections import defaultdict as dd
    rec = dd(lambda: {"chains":0,"kills":0,"pods":set()})
    for r in rs:
        m = r.get("machine")
        if not m: continue
        if r["event"]=="chain_done": rec[m]["chains"]+=1
        if r["event"]=="gate_kill":  rec[m]["kills"]+=1
        if "pod" in r: rec[m]["pods"].add(r["pod"])
    if not rec: print("(machine= 欄位樣本不足;租機時記得 log rented machine=<id>)"); return
    for m,v in sorted(rec.items(), key=lambda kv:-kv[1]["chains"]):
        tag = "→白名單候選" if v["chains"]>=1 and v["kills"]==0 else ("→黑名單候選" if v["kills"]>=2 else "")
        print(f"machine {m}: 鏈{v['chains']} 殺{v['kills']} pods{len(v['pods'])} {tag}")

def market(_):
    """快照當下合格 5090 offers 行情 → DB(建議 4h cron 呼叫,累積後看時段優惠)"""
    import subprocess
    key = open(os.path.expanduser("~/.vast-api-key")).read().strip()
    out = subprocess.run(["vastai","search","offers",
        "gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>70",
        "-o","dph+","--raw","--api-key",key], capture_output=True, text=True, timeout=60).stdout
    o = json.loads(out)
    ok = sorted(x["dph_total"] for x in o
        if x.get("dph_total",9)<2 and (x.get("inet_down_cost") or 0)<=0.005
        and x.get("disk_bw",0)>=4000 and float(x.get("cuda_max_good") or 0)>=13.0)
    rec = {"n": len(ok)}
    if ok: rec.update(p10=round(pct(ok,10),3), p50=round(pct(ok,50),3), lo=round(ok[0],3))
    log(["market"] + [f"{k}={v}" for k,v in rec.items()])
    # 地區別快照(觀察「深夜/凌晨時段該區更便宜」假設)
    from collections import defaultdict as dd
    geo = dd(list)
    for x in o:
        if x.get("dph_total",9)<2 and (x.get("inet_down_cost") or 0)<=0.005 \
           and x.get("disk_bw",0)>=4000 and float(x.get("cuda_max_good") or 0)>=13.0:
            g=(x.get("geolocation") or "?").split(",")[-1].strip()
            geo[g].append(x["dph_total"])
    for g, xs in sorted(geo.items(), key=lambda kv:-len(kv[1]))[:6]:
        log(["market_geo", f"geo={g}", f"n={len(xs)}", f"p50={round(pct(sorted(xs),50),3)}", f"lo={round(min(xs),3)}"])

def cost(_):
    """由 DB 實測值輸出成本公式與現值(720P/141f/20步/int8+sage 基準)"""
    rs = rows()
    cs  = [r["secs"] for r in rs if r["event"]=="chain_done" and "secs" in r]
    ttr = [r["min"] for r in rs if r["event"]=="running" and "min" in r]
    waste = sum(r.get("cost",0) for r in rs if r["event"]=="gate_kill")
    prod_h = sum(r.get("hours",0) for r in rs if r["event"]=="destroyed")
    mkt = [r for r in rs if r["event"]=="market" and "p10" in r]
    dph = mkt[-1]["p10"] if mkt else 0.55
    chain = pct(cs,50) if cs else 520          # 294f 鏈實測中位
    per_shot = chain/2                          # 141f 鏡
    cold_min = (pct(ttr,50) or 5) + 8           # 拉映像+模型DL+載入
    wr = waste/max(prod_h*dph,0.01) if prod_h else 0.15  # 殺 pod 攤提率,樣本不足先抓 15%
    print(f"成本公式(參數全由 DB 更新,n_chain={len(cs)}, n_run={len(ttr)}):")
    print(f"  每鏡成本 = (鏡秒 {per_shot:.0f}s + 冷啟 {cold_min:.0f}min×60/每pod鏡數) /3600 × dph × (1+殺攤 {wr:.0%})")
    for shots_per_pod in (3,5,8):
        c = (per_shot + cold_min*60/shots_per_pod)/3600 * dph * (1+wr)
        print(f"  每pod跑{shots_per_pod}鏡: ${c:.3f}/鏡  → 3分鐘片(31鏡): ${c*31:.2f}")
    print(f"  行情 dph=P10 ${dph}/hr" + (f"(快照{len(mkt)}筆)" if mkt else "(無快照,用預設)"))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"log": log, "report": report, "suggest": suggest, "market": market, "cost": cost, "hosts": hosts}[cmd](sys.argv[2:])
