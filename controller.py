#!/usr/bin/env python3
"""Fan-out controller for MiniMax-H3 (or any ComfyUI workflow) across N worker endpoints.

Model:
  - Each WORKER is a ComfyUI HTTP endpoint (a cloud 5090 pod, or localhost for a smoke test).
  - You export your working workflow from ComfyUI (Save (API Format)) -> template.json.
  - project.json lists SHOTS; each shot supplies values to inject into the template
    (prompt/seed/reference-image paths/output prefix...) via an `inject` map of field -> [node_id, input_key].
  - Controller assigns shots to free workers (work-queue, load-balanced), submits /prompt,
    polls /history, downloads each produced file via /view. Resumable (skips shots already collected).

This is provider-agnostic: it only needs a list of worker base URLs. Spinning the pods up
(RunPod etc.) is done separately (see runpod_pool.sh); paste their URLs into workers.txt.

Usage:
  python controller.py --project project.json --template template.json \
      --workers workers.txt --out ./outputs [--concurrency-per-worker 1]

workers.txt: one worker base URL per line, e.g.  https://abc-8188.proxy.runpod.net
             (or http://127.0.0.1:8189 for a local smoke test)
"""
import argparse, json, os, sys, time, threading, queue, urllib.request, urllib.parse, urllib.error, copy

def http_json(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def http_get(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()

def worker_alive(base):
    try:
        http_get(base.rstrip("/") + "/system_stats", timeout=8); return True
    except Exception:
        return False

def set_by_path(wf, node_id, key, value):
    if node_id not in wf:
        raise KeyError(f"node '{node_id}' not in template; check inject map")
    wf[node_id]["inputs"][key] = value

def submit_and_wait(base, wf, shot_id, poll=5, hard_timeout=3600):
    base = base.rstrip("/")
    pid = http_json(base + "/prompt", {"prompt": wf})["prompt_id"]
    t0 = time.time()
    while True:
        time.sleep(poll)
        try:
            h = http_json(base + f"/history/{pid}", timeout=20)
        except Exception:
            continue
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(f"[{shot_id}] worker error: "
                                   f"{json.dumps(st.get('messages', [])[-2:], ensure_ascii=False)[:600]}")
            if st.get("completed"):
                return h[pid].get("outputs", {})
        if time.time() - t0 > hard_timeout:
            raise TimeoutError(f"[{shot_id}] timed out after {hard_timeout}s")

def collect_outputs(base, outputs, dest_dir, shot_id):
    base = base.rstrip("/"); saved = []
    for _node, o in outputs.items():
        for item in o.get("gifs", []) + o.get("videos", []) + o.get("images", []):
            fn = item.get("filename"); sub = item.get("subfolder", ""); typ = item.get("type", "output")
            if not fn:
                continue
            q = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
            data = http_get(base + "/view?" + q, timeout=300)
            ext = os.path.splitext(fn)[1] or ".bin"
            out = os.path.join(dest_dir, f"{shot_id}{ext}")
            with open(out, "wb") as f:
                f.write(data)
            saved.append(out)
    return saved

def build_wf(template, inject_map, fields, out_prefix, prefix_field):
    wf = copy.deepcopy(template)
    for name, val in fields.items():
        if name not in inject_map:
            raise KeyError(f"field '{name}' has no inject mapping")
        nid, key = inject_map[name]
        set_by_path(wf, nid, key, val)
    # force a unique, predictable output prefix so /view + resume work
    if prefix_field in inject_map:
        nid, key = inject_map[prefix_field]
        set_by_path(wf, nid, key, out_prefix)
    return wf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--workers", required=True)
    ap.add_argument("--out", default="./outputs")
    ap.add_argument("--concurrency-per-worker", type=int, default=1,
                    help="parallel jobs per worker (keep 1 for heavy H3 on a single GPU)")
    args = ap.parse_args()

    project = json.load(open(args.project))
    template = json.load(open(args.template))
    inject_map = project["inject"]                 # field -> [node_id, input_key]
    prefix_field = project.get("prefix_field", "output_prefix")
    shots = project["shots"]                        # list of {id, fields:{...}}
    os.makedirs(args.out, exist_ok=True)

    workers = [l.strip() for l in open(args.workers) if l.strip() and not l.startswith("#")]
    workers = [w for w in workers if worker_alive(w)]
    if not workers:
        print("No live workers. Check workers.txt / that pods are up."); sys.exit(1)
    print(f"[controller] {len(workers)} live worker(s), {len(shots)} shot(s)")

    # load-balanced pool: one slot per (worker x concurrency)
    pool = queue.Queue()
    for w in workers:
        for _ in range(max(1, args.concurrency_per_worker)):
            pool.put(w)

    lock = threading.Lock(); done = {"ok": 0, "fail": 0, "skip": 0}
    def run_shot(shot):
        sid = str(shot["id"])
        # resume: skip if we already collected something for this shot
        existing = [f for f in os.listdir(args.out) if f.startswith(sid + ".")]
        if existing:
            with lock: done["skip"] += 1
            print(f"[{sid}] already collected ({existing[0]}), skip"); return
        w = pool.get()
        try:
            wf = build_wf(template, inject_map, shot["fields"], out_prefix=f"fanout_{sid}",
                          prefix_field=prefix_field)
            t0 = time.time()
            outs = submit_and_wait(w, wf, sid)
            saved = collect_outputs(w, outs, args.out, sid)
            with lock: done["ok"] += 1
            print(f"[{sid}] ok on {w} in {time.time()-t0:.0f}s -> {saved}")
        except Exception as e:
            with lock: done["fail"] += 1
            print(f"[{sid}] FAILED on {w}: {e}")
        finally:
            pool.put(w)   # return the slot (even on failure) so the queue drains

    threads = [threading.Thread(target=run_shot, args=(s,)) for s in shots]
    for t in threads: t.start()
    for t in threads: t.join()
    print(f"[controller] done: ok={done['ok']} fail={done['fail']} skip={done['skip']} -> {args.out}")
    sys.exit(1 if done["fail"] else 0)

if __name__ == "__main__":
    main()
