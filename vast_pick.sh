#!/usr/bin/env bash
# 選 Vast 5090 host 的標準規則(2026-08-11 教訓後):
# 1) 頻寬免費(inet_down_cost==0)優先;否則 <=0.005/GB
# 2) disk_bw >= 5000 MB/s(慢碟會拖慢載入/解碼 ~2x)
# 3) 按 $/hr 升序
~/.local/bin/vastai search offers 'gpu_name=RTX_5090 num_gpus=1 rentable=true verified=true disk_space>60' -o 'dph+' --raw 2>/dev/null | python3 -c "
import sys,json
o=json.load(sys.stdin)
def ok(x,maxbw):
    return x.get('dph_total',9)<0.55 and (x.get('inet_down_cost') or 0)<=maxbw and x.get('disk_bw',0)>=5000 and float(x.get('cuda_max_good') or 0)>=13.0
free=[x for x in o if ok(x,0)]
cheap=[x for x in o if ok(x,0.005)]
pool=free or cheap
tag='FREE-BW' if free else 'CHEAP-BW'
for x in sorted(pool,key=lambda r:r.get('dph_total',9))[:5]:
    print(f\"{x['id']}  {tag}  \${x['dph_total']:.3f}/hr  bw=\${(x.get('inet_down_cost') or 0):.3f}/GB  disk_bw={x.get('disk_bw',0):.0f}  {str(x.get('geolocation'))[:16]}\")
"