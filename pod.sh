#!/usr/bin/env bash
# Control the RunPod 5090 pod via REST API. Key read from ~/.runpod-key (never printed).
#   pod.sh status | start | stop | kill | url
# start = resume the EXITED pod (container+deps intact) + relaunch ComfyUI on :8188.
# stop  = pause (GPU billing stops). kill = terminate (volume kept).
set -uo pipefail
K=$(cat ~/.runpod-key)
POD=${POD_ID:-sa2wqrxrd4irvh}
SSHUSER=${POD_SSH:-sa2wqrxrd4irvh-64411fd9}
API=https://rest.runpod.io/v1
KEYF=~/.ssh/id_rsa
api(){ curl -s -m30 -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"; }
url(){ echo "https://${POD}-8188.proxy.runpod.net"; }
st(){ api "$API/pods/$POD" | python3 -c "import sys,json;d=json.load(sys.stdin);print('status='+str(d.get('desiredStatus')),'running='+str(bool(d.get('runtime'))),'cost=\$'+str(d.get('costPerHr'))+'/hr')" 2>/dev/null; }
launch_comfy(){ # start ComfyUI in background on the pod via proxy SSH
  timeout 40 ssh -i "$KEYF" -tt -o StrictHostKeyChecking=no -o ConnectTimeout=25 "$SSHUSER@ssh.runpod.io" 2>/dev/null <<'E' | tr -d '\r' | grep -aE "COMFY_LAUNCHED" | tail -1
pgrep -f "main.py --listen" >/dev/null || (cd /workspace/ComfyUI && nohup python main.py --listen 0.0.0.0 --port 8188 >/workspace/comfy.log 2>&1 &); sleep 3; echo COMFY_LAUNCHED
exit
E
}
case "${1:-status}" in
  status) st ;;
  url) url ;;
  start)
    echo "resuming $POD ..."; api -X POST "$API/pods/$POD/start" >/dev/null
    for i in $(seq 1 40); do
      s=$(api "$API/pods/$POD" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('desiredStatus'), 'RT' if d.get('runtime') else '--')" 2>/dev/null)
      echo "  [$i] $s"; echo "$s" | grep -q "RUNNING RT" && break; sleep 6
    done
    echo "launching ComfyUI ..."; launch_comfy
    echo "READY -> $(url)  ($/hr billing is ON now; run 'pod.sh stop' when done)"
    ;;
  stop) echo "stopping $POD ..."; api -X POST "$API/pods/$POD/stop" >/dev/null; sleep 2; st ;;
  kill|terminate) echo "TERMINATING $POD (volume $VOL kept) ..."; api -X DELETE "$API/pods/$POD" >/dev/null; echo "terminated"; ;;
  *) echo "usage: pod.sh status|start|stop|kill|url" ;;
esac
