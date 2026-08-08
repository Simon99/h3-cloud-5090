# 雲 5090 方案(最終版)

_H3 生成 + 放大 一條龍,隨時可用、可 1 台或 N 台並行。彙整 2026-08-08。細節見同目錄各檔。_

## A. 已定的核心決策
1. **卡 = RTX 5090（32GB Blackwell）**。剛好夠 H3(峰值 <30GB)、原生 nvfp4。
   - ❌ 不用 **B200**(192GB 過殺、貴 5–20×,H3 用不到)。
   - ❌ 不用 **GCP/AWS/Azure**(租不到 GeForce、資料中心卡更貴且無 nvfp4)。
   - 例外:哪天要**訓練**或跑**塞不下 32GB 的大模型**才上 B200/H200。
2. **生成為主、放大為輔**。**720P（1312×736)是 H3 原生天花板**(模型限制)。
   - 目標 720P → **直接生、不放大**。
   - 目標 1080p/4K → 生 720P native 再 FlashVSR 收尾(從乾淨底放大)。
3. **不 24/7 開機**。GPU 按秒 on-demand、**無最低租期**;唯一常態費 = 選擇性的硬碟。
4. **fan-out**。每 shot 獨立 → 可 N 台並行,**同一套 controller**;並行**不加錢只換時間**;**每台 4–6 鏡**最優(別 1 鏡 1 台,模型載入吃掉一半)。

## B. 供應商(按路線)
| 路線 | 首選 | 為什麼 | 開機腳本 |
|---|---|---|---|
| **A 單機「隨時可用」** | **RunPod** ~$0.99/hr | 真 Network Volume(養一次、開機即用)| `runpod_pool.sh` |
| **B fan-out 最便宜** | **Vast.ai** $0.27–0.53(挑 verified)/ **Salad** ~$0.20 | 烤映像不靠網路碟,正好避開其持久性弱點 | `vast_pool.sh` |
> controller / Dockerfile / provision **三家通用**,只有 pool 腳本各一支。

## C. 操作(兩條路線)
**路線 A（先做這個,上手)**:建 Network Volume(同 5090 region)→ 開 5090 pod 掛碟 → `bash provision.sh all` 養環境 → Terminate(碟留著)。之後開機即用。
**路線 B（要並行再升）**:`docker build --build-arg BAKE_MODELS=1 … && push` → 建 template → `vast_pool.sh up N` → controller 派工 → `down` 全關。
**每次跑**:開 pod → 拿 ComfyUI URL 進 `workers.txt` → ComfyUI 匯出 `template.json` + 填 `project.json` → `python controller.py …` → 組裝 →(要 1080p+ 才)FlashVSR → **Terminate**。

## D. 成本(÷5 初估,待實測校正)
| 項目 | 時間 | 成本 @$0.99/hr |
|---|--:|--:|
| 每鏡生成(960×544 基準,÷5)| ~122s | ~$0.03 |
| 全片 23 鏡 · 960×544 | ~47 min（4 台 fan-out ~12 min)| ~$0.77 |
| **全片 · 720P native(推薦,超線性)** | ~2.5–3 h(4 台 ~45 min)| **~$2.5–3** |
| 放大 FlashVSR(僅 1080p/4K 才需)| ~19 min | ~$0.3 |
| **常態(只留 130GB 硬碟)** | — | **~$8–9/月** |
- 720P 直接生 = 成品,**無額外放大成本**。Vast/Salad 走 fan-out 可再砍算力一半以上。
- **每分鐘成品 GPU 成本**:960×544 ~$0.34;720P native ~$1.1–1.3;+FlashVSR 1080p +~$0.15(RunPod;Vast 約一半)。

## D2. 儲存策略(三選一,決定要不要那 $9/月)
| 策略 | 月固定 | 每次開機 | 適合 |
|---|--:|---|---|
| **留 Network Volume** | **~$9** | 即開即用、零等待 | **每週用多次** |
| **刪 volume + 開機下載** | **$0** | ~$0.25 GPU + 等 10–20 分(下 65GB,計費中)| 偶爾用、不想搞映像 |
| **烤 Docker 映像(BAKE_MODELS=1)** | **~$0**(Docker Hub 公開免費)| 拉映像(host 有 cache 就快、無 HF 下載)| **偶爾用又想少等 / fan-out** |
- **打平點**:留 volume $9 ÷ 重下 ~$0.25 ≈ **每月 36 次**。用少於 ~36 次 → 別留 volume。
- **重下不是免費**:它在計費中的 5090 上跑 → ~$0.25 + 等待。烤映像可避開 HF 下載、且 fan-out 每台一致。
- 建置映像:`PUSH=1 ./build_image.sh youruser/h3-worker:1`(建議在網路快的機器 build;會下 65GB + push ~70GB,一次性)。

## E. 已備好(`cloud-5090/`,本機能驗的都驗過)
- `controller.py`(派工+收集+resume,**本機對 ComfyUI 實測過**)、`Dockerfile`/`provision.sh`(模型路徑對 HF 核 206)/`worker_start.sh`、`runpod_pool.sh`+`vast_pool.sh`、`project.example.json`+可重跑的 `*_smoke.json`、`RENT-5090-runbook.md`、`PROVIDERS.md`。
- ⏳ 待硬體才能驗:映像 build(cu128)、跨 pod 多機並行、5090 上 H3 nvfp4/720P 速度(校 ÷5)。

## F. 你動手的最短路徑
1. 租 RunPod 5090 + 建 130GB volume。
2. `bash provision.sh all`(養環境)。
3. ComfyUI 拉 H3 工作流 → `Save (API Format)` → 對照 node id 填 `project.json` 的 inject。
4. `python controller.py …` 派工。
> 之後要壓成本做大量並行,再把映像丟 Vast/Salad 跑路線 B。
