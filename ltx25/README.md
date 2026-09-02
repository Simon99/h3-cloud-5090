# LTX-2.5 on RTX 5090 — 已驗證流程整理

> 2026-09-03 於 RunPod RTX 5090(32GB)實測全通。三種模式(文生 / 首尾幀 / 多鏡長片)共用同一套兩段式蒸餾接線,原生輸出 **1920×1088 + 音訊**,121 幀 83–110 秒。
> 完整跑手原始碼:[Simon99/h3-cloud-5090 → `ltx25_run.py`](https://github.com/Simon99/h3-cloud-5090)

---

## 1. 環境門檻(先過這關,不然全卡)

| 項 | 要求 | 說明 |
|---|---|---|
| ComfyUI | **≥ 0.34**(實測 0.34.3) | 0.31 有 LTX 節點但 gemma4 文字編碼器跑不動,`CLIPTextEncode` 報 `not enough values to unpack (expected 4, got 1)`。機房拉 GitHub 常被限流,建議用 codeload tarball 升級:`curl -L https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/v0.34.3` 解開覆蓋 + `pip install -r requirements.txt`(requirements 不釘 torch,既有 torch 不會被動) |
| GPU | 5090 32GB 實測 OK | nvfp4 量化是 Blackwell 原生格式 |
| 節點簽名 | **以機器上的 `/object_info` 為準** | 版本間會漂移(如 `LTXVEmptyLatentAudio` 從 `length` 改成 `frames_number`+`audio_vae`),別照舊教學抄 |

## 2. 模型檔(共 37.5GB,全部在 HF `Lightricks/LTX-2.5`)

| 檔 | 放哪 | 大小 |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` | `models/diffusion_models/` | 18.7GB |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `models/text_encoders/` | 15.4GB |
| `ltx-2.5-video-vae-conv-bf16.safetensors` | `models/vae/` | 1.5GB |
| `ltx-2.5-audio-vae-bf16.safetensors` | `models/vae/` | 0.4GB |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `models/latent_upscale_models/` | 1.0GB |

下載記得逐檔驗大小(比對上表),LFS 指標檔/錯誤頁存成 `.safetensors` 是常見靜默炸點。

## 3. 共同骨架:兩段式蒸餾(9 步 + 3 步)

低解析度採樣 → latent 2× 放大 → 少步精修。**CFG=1.0、euler_ancestral、24fps**,不用負向引導強度(negative 仍要接,給空字串即可)。

```
UNETLoader(nvfp4)          CLIPLoader(gemma4, type=ltxv)
        │                          │
        │            CLIPTextEncode(正/負) → LTXVConditioning(frame_rate=24)
        │                          │
EmptyLTXVLatentVideo(960×544×121)  │   LTXVEmptyLatentAudio(frames_number=121, frame_rate=24, audio_vae)
        └────────── LTXVConcatAVLatent ──────────┘
                           │
      ── Stage 1:SamplerCustomAdvanced ──
      ManualSigmas: 1.0, 0.99375, 0.9875, 0.98125, 0.975,
                    0.909375, 0.725, 0.421875, 0.0   (9 步)
                           │
                LTXVSeparateAVLatent
                    │(video)   │(audio)
     (flf2v 在這裡 LTXVCropGuides!見 §5)
                    │
        LTXVLatentUpsampler(spatial x2)
                    │
        LTXVImgToVideoInplace(bypass=True)†
                    │
        LTXVConcatAVLatent(接回 audio latent)
                           │
      ── Stage 2:SamplerCustomAdvanced ──
      ManualSigmas: 0.85, 0.7250, 0.4219, 0.0   (3 步)
                           │
                LTXVSeparateAVLatent
                    │(video)              │(audio)
VAEDecodeTiled(512/64/64/8)      LTXVAudioVAEDecode
                    └──── CreateVideo(fps=24) ────┘
                           │
                        SaveVideo
```

† `LTXVImgToVideoInplace` 的 `image` 是必填口,純 t2v 沒圖可餵——接一個 `EmptyImage`(64×64 黑圖)+ `bypass=True` 讓它旁路即可。

## 4. 流程一:t2v 文生(121f,83 秒)

上面骨架照跑即可。prompt 建議把「畫風 + 角色 + 動作 + 環境音描述」寫成一段,音訊是跟著 prompt 生的(寫 `Arena crowd noise and impact sounds` 就有對應音場)。

## 5. 流程二:flf2v 首尾幀鎖定(121f,~100 秒)

在骨架上加四個節點、動一個位置:

1. 首幀與尾幀各走 `LoadImage → LTXVPreprocess(img_compression=18) → LTXVAddGuide`
2. `LTXVAddGuide` 串接(第一顆管 `frame_idx=0`,第二顆管 `frame_idx=-1`),positive/negative/latent 逐級傳遞
3. **關鍵坑:`LTXVCropGuides` 必須放在 Stage 1 之後、latent 放大之前**(接 `LTXVSeparateAVLatent` 的 video 口,輸出的 positive/negative/latent 再進放大與 Stage 2)。放到最後才裁會炸 `keyframe_idxs holds N tokens, which is not a whole number of ...`——guide 幀的座標是低解析度網格,放大後對不上。

## 6. 流程三:mshot 多鏡一次生成(241f,~155 秒)

骨架不變,只改兩件事:`frames_number`/`length` 都設 241,prompt 用長文分鏡(每鏡一句、含鏡位描述)。單發 10 秒,模型會自己切鏡。

## 7. 實測數據(RTX 5090)

| 模式 | 幀數 | 生成時間 | 輸出 |
|---|---|---|---|
| t2v | 121 | **83s** | 1920×1088 + AAC |
| flf2v ×3 | 121 | 100–110s | 同上 |
| mshot | 241 | ~155s | 同上(10 秒) |

雲端成本參考:COMMUNITY 5090($0.69/hr)一顆 pod 37 分鐘跑完上述五發,約 **$0.43**(模型下載 43GB 約 12 分)。

## 8. 踩坑清單(照序排雷)

1. **ComfyUI 太舊**:節點都在、提交驗證也過,跑起來才在 TE 炸——版本先驗(`/system_stats` 的 `comfyui_version`),別信「節點存在=支援」。
2. **簽名漂移**:同名節點跨版本改必填口,建圖前先拉 `/object_info/<節點名>` 對一次。
3. **flf2v 裁切位置**(§5):錯誤訊息其實把解法寫明了,照做即通。
4. **Inplace 必填 image**(§3 †):bypass 也要餵假圖。
5. **下載驗大小**:gated repo 抓檔要帶 token,失敗時錯誤頁會被存成模型檔,載入時才炸——下載後立刻 `stat` 比對預期大小。

---

## 9. 本資料夾與 repo 內相關檔案

| 檔 | 用途 |
|---|---|
| `ltx25/README.md` | 本文件(流程+接線+坑) |
| `ltx25/precmd.sh` | pod 開機前置:ComfyUI 0.34.3 tarball 升級 + 模型五檔並行下載(含大小 gate) |
| `ltx25/jobs.example.txt` | 批次工作清單範例 |
| `../ltx25_run.py` | 跑手:build() 完整組 graph(t2v/flf2v 共用),提交+輪詢+快速失敗 |
| `../run_batch.sh` | 批次引擎:逐鏡「跑完→立刻下載→ffprobe 驗證」,續租心跳與收尾短引信 |
| `../runpod.py` | RunPod pod 管理(create 含 --precmd 口、觀測服務最先啟動、黑名單迴避) |

最小上手:`runpod.py create --precmd="$(cat ltx25/precmd.sh)"` 開機 → `RUNNER=ltx25_run.py run_batch.sh <podId> <outdir> ltx25/jobs.example.txt`。
