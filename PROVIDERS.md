# 供應商選擇(租 5090)

_價格/現貨每天變,查即時:[getdeploying](https://getdeploying.com/gpus/nvidia-rtx-5090)、[gpus.io](https://gpus.io/en/gpus/rtx5090)、[gpufinder](https://gpufinder.dev/gpu/rtx-5090)。_

**核心:我們的 `controller.py` / `Dockerfile` / `provision.sh` 都不綁供應商**——任何給你一個 ComfyUI HTTP endpoint 的家都能用,只有「開 N 台」的 pool 腳本各家不同。

## 對照表(2026,概略)
| 供應商 | 5090 $/hr | 持久儲存 | 可靠度 | 開機腳本 | 最適合 |
|---|--:|---|---|---|---|
| **RunPod** | ~$0.99 | ✅ 真 Network Volume(可重掛)| 高、省心 | `runpod_pool.sh` | **單機「隨時可用」、上手** |
| **Vast.ai** | **$0.27–0.53**(spot ~$0.1)| ⚠️ 綁單機 host | 看 host(挑 verified)| `vast_pool.sh` | **最便宜、fan-out 並行** |
| **SaladCloud** | **~$0.20 起** | 容器群、無持久碟 | 消費級、會中斷 | (用其 container-group API/portal)| 極致便宜、可容忍中斷的大量並行 |
| Runcrate | ~$0.45–0.55 | 看方案 | 中 | (改 runpod_pool 或手動)| 便宜固定價 |
| Lambda | ~$0.79 | ✅ 持久檔案系統 | 高、企業級 | (手動/API)| 穩定 |

## 依路線挑
- **路線 A「隨時可用」單機(要可重掛網路碟)→ RunPod**(Vast/Salad 的持久性弱,不適合養常駐碟)。
- **路線 B fan-out(烤映像、開 N 台)→ Vast.ai**(便宜一半+、烤映像不靠網路碟,正好避開其持久性弱點);**挑 verified / 高 reliability host**,否則當機/重啟讓實際成本 +20–40%。要穩就 RunPod。
- **只求最便宜、能忍中斷 → Salad / Vast spot**(~$0.1–0.2/hr);**長任務(跑到一半怕斷)別用 spot/Salad**。

## ❌ 不要用 GCP / AWS / Azure(這個問題常見)
- **Hyperscaler 不提供 GeForce**(NVIDIA 授權禁止)→ **根本租不到 5090**。
- 只有資料中心卡且更貴 + VM/碟/流量另計:GCP L4(24GB Ada,無 nvfp4)$0.70/hr all-in ~$1+;A100 80GB $5.07;H100 $11+。
- 對「H3 需 32GB Blackwell + nvfp4」它**沒有對應卡**。專用雲便宜 2–10 倍還給你正確的卡。
- GCP 只在:已有 GCP 基建/合規、超大持續負載簽 1–3 年 CUD、或 $300 新帳號額度先抵時才考慮。

## 開機腳本
- `runpod_pool.sh up N` — RunPod(需 runpodctl + template id)。
- `vast_pool.sh up N` — Vast.ai(需 `pip install vastai` + api-key);挑 verified 5090、開 N 台、產 `workers.txt`。
- 兩者都吐 `workers.txt` → 同一支 `controller.py` 派工。
