# Pkg 5 | nvfp4 builds (official templates default to int8 — no nvfp4 variant)

[中文版 →](README.zh.md)

Three workflows = the official files with exactly one change: the transformer swapped to
`ltx-2.5-22b-distilled-transformer-nvfp4.safetensors`. Drag into ComfyUI and run
(everything else matches the official defaults).

## Why swap
| Build | Size | For |
|---|---|---|
| int8-convrot (official default) | 21.5GB | general |
| **nvfp4 (this package)** | **18.7GB** | **native format on Blackwell (5090/B-series)** |

## Measured on a 5090 (ComfyUI 0.34.3 / torch 2.13+cu130)
| Mode | Frames | Gen time | Output |
|---|---|---|---|
| t2v | 121 | **83s** | 1920×1088 + audio |
| flf2v | 121 | 100–110s | same |
| t2v long | 241 | ~155s | 10 s |

Prereq: ComfyUI ≥ 0.34 (older builds can't run the gemma4 text encoder); model list in the parent README.
