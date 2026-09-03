# 包2|跨模型放大:任意影片 → LTX latent 2×(官方無跨家組合)

[English →](README.md)

用 LTX 的 latent spatial upscaler 放大**別家模型的輸出**(我們用在 MiniMax-H3 的 544P 上):
`任意mp4 → VAEEncode(LTX VAE) → LTXVLatentUpsampler 2× → VAEDecode → 1920×1088`

跑手 `ltx_up.py <輸入mp4> [輸出前綴]`(打本機 ComfyUI :8189 API)。
需要的模型只有兩個:LTX video VAE(1.5GB)+ spatial upscaler(1.0GB),8GB 卡可跑。

實測對比(2026-08-30,960×544→1920×1088):
| 方案 | 耗時 | 質感 |
|---|---|---|
| **LTX latent 2×** | **60s** | 乾淨,無光暈 |
| Real-ESRGAN | 526s | 數位光暈+塑膠感 |

為什麼值得:H3 在 544P/480P 生成同速(固定開銷平台期)→「雲端 544P + 本機 LTX 放大」
比雲端直出 736P 更快、解析度更高,還避開高解析度 VAE 解碼打死 ComfyUI 的風險。
注意:_pick_upscaler() 從 enum 自動挑檔名(硬編碼檔名曾三度因版本後綴踩坑)。
