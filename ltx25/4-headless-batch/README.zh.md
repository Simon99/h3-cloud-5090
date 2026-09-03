# 包4|headless 雲端批次(官方只有拖 UI 檔,無自動化)

[English →](README.md)

無人值守整條鏈:**開機 → 升級 ComfyUI → 下載模型(逐檔大小 gate)→ 版本 gate → 跑批 → 逐支下載+ffprobe 驗證 → 收租**。

| 檔 | 職責 |
|---|---|
| `precmd.sh` | 容器開機前置:codeload tarball 升級 0.34.3(避 git 機房限流)+ 五模型並行下載,每檔驗大小(防 LFS 指標/錯誤頁存成 .safetensors) |
| `ltx25_run.py` | API 直呼跑手:組 graph(t2v/flf2v 共用)、提交、輪詢;**提交回應 node_errors 非空即判死**(防 ComfyUI「部分輸出驗證失敗→靜默忽略→回 200」的假成功);ComfyUI 失聯 exit 2 |
| `run_batch.sh` | 批次引擎:每鏡「跑完→立刻下載→ffprobe 驗證」不等整批;背景續租心跳;exit 2 整批中止;結束把租約改 10 分短引信(防忘了關機) |
| `jobs.example.txt` | 工作清單:每行 `<輸出名> <參數...>`;prompt 類參數以 `+` 代空白 |

用法:
```bash
python3 runpod.py create --precmd="$(cat precmd.sh)"     # 見 repo 根目錄 runpod.py
RUNNER=ltx25_run.py bash run_batch.sh <podId> <outdir> jobs.example.txt
```
三道 gate 缺一不可——都是真金換的:版本 gate(0.31 節點在但 TE 跑不動)、
大小 gate(git-lfs 指標檔兩度炸 buffer)、node_errors gate(20 秒假成功)。
