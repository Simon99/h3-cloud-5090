# LTX-2.5 — 拖進 ComfyUI 就能跑

`workflows/` 三個官方 workflow 檔,拖進 ComfyUI 視窗即載入(採樣參數/sigmas/接線都在檔內,不用手接):

| 檔 | 用途 | 5090 實測 |
|---|---|---|
| `video_ltx2_5_t2v.json` | 文生影片(含音訊) | 121幀 83s,1920×1088 |
| `video_ltx2_5_flf2v.json` | 首尾幀鎖定 | 121幀 ~100s |
| `video_ltx2_5_i2v.json` | 圖生影片 | (同級) |

## 配置標註

1. **ComfyUI 必須 ≥ 0.34**(舊版有節點但 gemma4 文字編碼器跑不動)。
2. 模型檔全在 HF [`Lightricks/LTX-2.5`](https://huggingface.co/Lightricks/LTX-2.5),照資料夾放:

| 檔 | 放哪 | 大小 |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` ← **5090/Blackwell 選這顆**(模板預設 int8-convrot 21.5GB,較慢) | `models/diffusion_models/` | 18.7GB |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `models/text_encoders/` | 15.4GB |
| `ltx-2.5-video-vae-bf16.safetensors` | `models/vae/` | 1.5GB |
| `ltx-2.5-audio-vae-bf16.safetensors` | `models/vae/` | 0.4GB |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `models/latent_upscale_models/` | 1.0GB |

3. 載入後只要動三處:**UNET 下拉改選 nvfp4**、prompt、(flf2v)首尾兩張圖。其餘保持模板預設(CFG=1、兩段式 9+3 步蒸餾 sigmas)。
4. 模板另引用 `gemma4_e2b_it_int8_convrot`(prompt 改寫)與 vocoder,缺檔時把對應節點 bypass 掉即可,不影響主鏈。
5. 下載驗大小:gated repo 要帶 HF token,錯誤頁被存成 .safetensors 是常見靜默炸點。

## 批次/雲端自動化(可選)

`precmd.sh`(RunPod 開機自動升級 ComfyUI+下載模型)、`jobs.example.txt` + repo 根目錄 `ltx25_run.py`(API 直呼跑手)/`run_batch.sh`(逐鏡下載驗證)。
