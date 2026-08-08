# Cloud 5090 — fan-out H3 生成 + 放大(可 1 台或 N 台並行)

一套「無狀態 worker 映像 + 派工控制器」的片廠。**同一套碼**:租 1 台 5090 慢慢跑,或開 N 台把每個 shot 分出去並行——成本幾乎一樣,只換牆鐘。⚠️ 這是**部署後才驗證**的骨架(本機沒有 5090);`controller.py` 的派工邏輯可先對本機 ComfyUI(當作 1 台 worker)smoke test。

## 架構
```
project.json (shots) + template.json (你從 ComfyUI 匯出的工作流)
        │
   controller.py  ── 派工/負載平衡/收集(純 stdlib)
        │  每個 shot 注入參數 → POST /prompt → 輪詢 /history → /view 下載
        ▼
  worker ×N  = ComfyUI + H3/FlashVSR 節點(Docker 映像,無狀態)
        │  模型:烤進映像 或 開機下載(不是 N 顆付費硬碟!)
        ▼
  outputs/  ← 各 shot 收回本機 → 組裝 /(選配)放大 → 交付
```
**關鍵**:模型放「一個映像來源」,每台落到 pod **內含的容器盤**;**不需要每台一顆 persistent volume**。硬碟不隨台數增加。

## 檔案
| 檔 | 作用 |
|---|---|
| `Dockerfile` | worker 映像(Blackwell/cu128 + ComfyUI + 節點 + FlashVSR patch;可選烤模型)|
| `provision.sh` | 裝節點/patch(`nodes`)+ 下模型(`models`)|
| `worker_start.sh` | pod entrypoint:缺模型就補,起 ComfyUI(`--listen 0.0.0.0 --port 8188`)|
| `controller.py` | 派工控制器(workflow-agnostic)|
| `project.example.json` | 專案 schema:`inject`(欄位→[node_id,input_key])+ `shots` |
| `runpod_pool.sh` / `vast_pool.sh` | 選配:RunPod/Vast 開/關 N 台並產 `workers.txt` |
| `PROVIDERS.md` / `RENT-5090-runbook.md` | 供應商選擇 + 租卡流程 |

## 一次性建置
```bash
# 1. 建映像(lean;或 --build-arg BAKE_MODELS=1 烤進 ~70GB)
docker build -t YOURUSER/h3-worker:1 .
docker push YOURUSER/h3-worker:1
# 2. RunPod 建一個 template 指向這映像、GPU=RTX 5090、expose 8188/http
#    （選 volume 掛在同區域可省下每次下模型;fan-out 大量並行則靠烤進映像）
```

## 每次跑(fan-out)
```bash
# A. 開 pool（或手動在 RunPod 開 N 台,把 proxy URL 貼進 workers.txt）
RUNPOD_TEMPLATE_ID=xxxx ./runpod_pool.sh up 4      # -> workers.txt (4 台)

# B. 在 ComfyUI 把你的 H3 工作流 Save (API Format) -> template.json
#    對照 template.json 的 node id,填 project.json 的 inject 映射

# C. 派工(1 台或 N 台同一指令)
python controller.py --project project.json --template template.json \
       --workers workers.txt --out ./outputs

# D. 收工:組裝 + 選配放大(沿用 upscale-exp/ 的腳本)
#    ffmpeg concat outputs/shot*.mp4 → 混旁白 → (要 1080p+ 才) FlashVSR

# E. 關 pool（停止計費;只剩硬碟/映像)
./runpod_pool.sh down
```
本機 smoke test(不用雲):`echo http://127.0.0.1:8189 > workers.txt` 對現有 ComfyUI-H3 跑 controller,驗證派工/收集邏輯(用一個本機能跑的 template)。

## 成本與並行(5090,按秒;÷5 初估待實測)
| 切法(23 鏡)| 牆鐘 | 算力成本 |
|---|--:|--:|
| 1 台 | ~47 min | ~$0.77 |
| **4 台 × 6 鏡** | **~12 min** | ~$0.8 |
| 23 台 × 1 鏡 | ~3.5 min | ~$0.9(overhead 高、湊卡難)|
- 總 GPU 秒數固定 → **並行不太加錢,只換時間**。別「1 鏡 1 台」:模型載入 ~60–90s 會吃掉一鏡(~122s)一半。**每台 4–6 鏡最划算。**
- 硬碟:映像烤模型 → **0 顆付費 volume**;只有產出需要收(controller 直接 /view 拉回,免物件儲存)。
- 常態不開 GPU = $0(或留一顆小 volume 放 code/產出)。

## 生成 vs 放大(接前面結論)
- **5090 原生上限 ~720P(1312×736)= H3 模型限制**。720P 目標 → 直接生、**不放大**。
- 只有要 **1080p/4K** 才在收工端加 FlashVSR(從 720P 乾淨底放大)。映像已裝好放大節點,備而不用。

## 部署前要確認/填的洞
1. **base 映像 cu128 tag** 抓當前可用版(Blackwell sm_120 必須 cu128+)。
2. **H3 模型確切檔名/路徑**:對 `Comfy-Org/MiniMax-H3` repo tree 核對(5090 用 nvfp4 編碼器 + fp8/bf16 diffusion)。
3. **template.json 的 node id → inject 映射**:每個工作流不同,匯出後對照填。
4. **runpodctl 旗標**:對你的版本核對;或 RunPod 網頁手動開 pod 貼 URL。
5. **region**:5090 現貨 + (若用)volume 要同一資料中心。

## 已在本機驗證(2026-08-08,對 ComfyUI-H3 當 1 worker)
- `controller.py` 全流程:派工 → `/prompt` → 輪詢 `/history` → `/view` 下載 → 存 per-shot ✅(用 FlashVSR 工作流當 template,2 個 clip 當 shots,產出 2×1088 正確)。
- resume 跳過已完成 ✅;worker 掛掉優雅報錯不卡死 ✅。
- 已驗證的本機範例:`template_smoke.json` + `project_smoke.json`(FlashVSR 放大版,可直接 `--workers workers.example.txt` 重跑)。
- 模型下載路徑全部對 HF 核對 200/206 ✅(H3 去掉 split_files/ 前綴、FlashVSR 用 FlashVSR1_1/TCDecoder 等真實檔名)。
- FlashVSR block-sparse→SDPA 的 sed patch 正則已測中 ✅。
- ⏳ 未驗證(需硬體):Docker 映像 build(Blackwell/cu128)、跨 pod 多機並行、5090 上 H3 nvfp4/720P 生成、runpodctl。
