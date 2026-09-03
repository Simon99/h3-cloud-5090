# 包5|nvfp4 檔位(官方模板預設 int8,無 nvfp4 版)

[English →](README.md)

三個工作流 = 官方檔唯一改動:transformer 換 `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors`。
拖進 ComfyUI 即用(其餘設定與官方一致)。

## 為什麼換
| 檔位 | 大小 | 適用 |
|---|---|---|
| int8-convrot(官方預設) | 21.5GB | 通用 |
| **nvfp4(本包)** | **18.7GB** | **Blackwell(5090/B系列)原生格式** |

## 5090 實測數據(2026-09-03,ComfyUI 0.34.3 / torch 2.13+cu130)
| 模式 | 幀數 | 生成時間 | 輸出 |
|---|---|---|---|
| t2v | 121 | **83s** | 1920×1088+音訊 |
| flf2v | 121 | 100-110s | 同上 |
| t2v 長片 | 241 | ~155s | 10 秒 |

前提:ComfyUI ≥0.34(舊版 gemma4 文字編碼器跑不動);模型清單見上層 README。
