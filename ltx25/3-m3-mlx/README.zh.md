# 包3|ltx-2-mlx:Apple Silicon 跑 LTX-2(官方 ComfyUI 生態外)

[English →](README.md)

專案:[dgrauet/ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx)(MLX 原生移植)。
實測機:M3 Ultra;q8 權重 ~82GB 磁碟。

## 安裝與生死線
```bash
git clone https://github.com/dgrauet/ltx-2-mlx && cd ltx-2-mlx
pip install -r requirements.txt
# ffmpeg 鏈(缺一即 mux 壞檔/找不到 ffprobe):
pip install "imageio-ffmpeg>=0.7.1" static-ffmpeg   # imageio 帶 ffmpeg 7.1;static-ffmpeg 只用它的 ffprobe
```
- **`--low-ram` 必加**:不加的話 VAE 解碼會把整機記憶體壓死(實測 M3 失聯數小時,只能硬重開)
- static-ffmpeg 的 ffmpeg 7.0 會 mux 出壞檔——影片編碼走 imageio 的 7.1,ffprobe 才用 static

## 已驗證跑法
```bash
# 蒸餾版文生(480p 實測 ~19s/步)
python generate.py --model distilled --prompt "..." --low-ram
# ic-lora(Clean-Plate 背景清除,已驗證可跑)
python generate.py --model distilled --ic-lora clean-plate --input in.mp4 --low-ram
```

## 定位
不追速度(5090 快一個量級),價值在:本地無雲費、隱私、以及 Mac 大統一記憶體能載 q8 全精度層。
