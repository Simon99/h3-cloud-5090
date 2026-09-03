# Pkg 3 | ltx-2-mlx: LTX-2 on Apple Silicon (outside the ComfyUI ecosystem)

[中文版 →](README.zh.md)

Project: [dgrauet/ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx) (native MLX port).
Tested on: M3 Ultra; q8 weights take ~82GB of disk.

## Install & the lifeline
```bash
git clone https://github.com/dgrauet/ltx-2-mlx && cd ltx-2-mlx
pip install -r requirements.txt
# ffmpeg chain (missing either one = corrupt mux / no ffprobe):
pip install "imageio-ffmpeg>=0.7.1" static-ffmpeg   # imageio ships ffmpeg 7.1; use static-ffmpeg ONLY for its ffprobe
```
- **`--low-ram` is mandatory**: without it the VAE decode eats the whole machine's memory
  (measured: an M3 unreachable for hours, hard reboot only)
- static-ffmpeg's ffmpeg 7.0 muxes corrupt files — encode via imageio's 7.1, use static only for ffprobe

## Verified invocations
```bash
# distilled text-to-video (~19s/step at 480p measured)
python generate.py --model distilled --prompt "..." --low-ram
# ic-lora (Clean-Plate background removal, verified working)
python generate.py --model distilled --ic-lora clean-plate --input in.mp4 --low-ram
```

## Positioning
Not about speed (a 5090 is an order of magnitude faster). The value: no cloud cost, privacy,
and Mac unified memory large enough for q8 full-precision layers.
