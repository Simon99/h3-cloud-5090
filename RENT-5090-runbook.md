# 租 5090:從零到能跑 — 操作流程

以 **RunPod** 為例(最省心)。更便宜的 Runcrate($0.55/hr)、Lambda($0.79/hr)步驟類似。
UI 標籤偶爾會變,以「概念」為準。⚠️ 核心觀念:**不 24/7 開機——GPU 想用才開、按秒付、用完 Terminate;唯一常態費用是你選擇保留的網路硬碟。**

---

## 0. 先決定(30 秒)
- **路線 A(先做這個)**:單機 + Network Volume。最快上手,適合 1 台跑。
- **路線 B(要並行再升)**:baked 映像 + N 台 fan-out。硬碟不隨台數增加。
- 兩條路線**同一支 `controller.py`**。

## 1. 開帳號 + 儲值(一次)
1. runpod.io 註冊。
2. **Billing → 加值 prepaid credit**(先放 $10 就好)。RunPod 是預付,花完自動停,不會爆帳。
3. 設 spending limit(保險)。

---

## 路線 A:單機 + Network Volume(先跑起來)

### A1. 先確認哪個 region 有 5090
Pods → Deploy → 篩 **RTX 5090** → 記下有現貨的資料中心(volume 要跟卡同一個 DC)。

### A2. 建 Network Volume(一次,~130GB ≈ $9/月)
Storage → Network Volumes → New → 選**上一步那個 region** → 130GB。

### A3. 開 5090 Pod
Pods → Deploy:
- GPU = **RTX 5090**,**On-Demand**(不要 Spot,長任務會被中斷)。
- Template 選 **CUDA 12.8 / PyTorch cu128** 的(Blackwell 必須;舊的會 `sm_120 not supported`)。或指定我們的映像。
- **掛上 A2 的 Network Volume**(通常 mount 到 `/workspace`)。
- Container Disk ~30GB;**Expose HTTP Port 8188**。
- Deploy。

### A4. 一次性裝環境(在 pod 上,~30–60 分,算力約 $0.5)
Connect → Web Terminal(或 SSH):
```bash
cd /workspace
git clone <你的 repo>            # 或 runpodctl send 把 cloud-5090/ 傳上去
cd cloud-5090
bash provision.sh all            # 裝節點+FlashVSR patch + 下 ~65GB 模型到 volume
bash worker_start.sh             # 起 ComfyUI（--listen 0.0.0.0:8188）
```
Connect → 8188 → 開 proxy URL(`https://<podid>-8188.proxy.runpod.net`)確認 ComfyUI 起來、能載模型、生一個測試 shot。

### A5. 存成「就緒狀態」
環境全在 volume 了 → **Terminate pod**(volume 留著)。之後要用再 Deploy 掛同一 volume,**~1–2 分就緒**。

---

## 日常使用(每次,路線 A)
1. Deploy pod(掛 volume)→ 自動起 ComfyUI。
2. Connect 拿 8188 的 proxy URL → 貼進本機 `workers.txt`。
3. ComfyUI 裡拉好工作流 → **Save (API Format)** → `template.json`;對照 node id 填 `project.json` 的 `inject` 與 `shots`。
4. 本機跑:
   ```bash
   python controller.py --project project.json --template template.json \
          --workers workers.txt --out ./outputs
   ```
5. 收工組裝(concat + 旁白 +(要 1080p+ 才)FlashVSR)。
6. **Terminate pod**(停算力費)。

---

## 路線 B:fan-out(要並行時再升)
1. build+push 映像(含模型):`PUSH=1 ./build_image.sh YOURUSER/h3-worker:1`(在網路快的機器;下 65GB + push ~70GB,一次性)。
2. RunPod 建 template 指向該映像、GPU=5090、expose 8188。
3. `RUNPOD_TEMPLATE_ID=xxx ./runpod_pool.sh up 4` → 自動開 4 台、產 `workers.txt`。
4. 同一支 `controller.py` 派工(自動負載平衡到 4 台)。
5. `./runpod_pool.sh down` 一次全關。
- 差別:B **不靠 volume**(模型烤映像裡),每台獨立可任意並行,硬碟 0 顆。

---

## 成本控制(必做)
- **用完一定 Terminate**——不是 Stop!(Stop 還在收容器盤/閒置費;Terminate 才真的停)。
- Network Volume 是唯一常態費(~$9/月);長期不用連 volume 一起刪 → $0。
- 一部 135s 片:生成~$0.77 +(要 1080p+)放大~$0.3,單次幾毛到一兩塊。
- prepaid + spending limit 雙保險。

## 一定會遇到的坑
| 坑 | 解 |
|---|---|
| `sm_120 not supported` | base 映像要 **cu128+**(Blackwell) |
| 5090 沒現貨 | 換 region;volume 要跟卡同 DC |
| FlashVSR `NoneType not callable` | `compatibility_mode` patch(provision.sh 已含)|
| H3 編碼器 | 5090 用 **nvfp4**(4060 用不了那顆)|
| Spot 中途斷 | 長任務用 On-Demand |

## 我這邊已備好的
`cloud-5090/`:Dockerfile / provision.sh(模型路徑已對 HF 核對)/ worker_start.sh / controller.py(本機已驗證派工+收集+resume)/ runpod_pool.sh / project.example.json + 一組可重跑的 `*_smoke.json`。
你只要:租卡 → 跑 provision → 匯出 template.json 填 inject → 派工。
