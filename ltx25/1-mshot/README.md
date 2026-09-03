# Pkg 1 | Multi-shot single generation (no official multi-shot template)

[中文版 →](README.zh.md)

Keep the official `video_ltx2_5_t2v.json` wiring untouched; change exactly two things:
1. **length → 241** (= 10 s; LTX frame rule is 8k+1, so 121/241 are both valid)
2. Swap the prompt for a "storyboard" style — see `mshot_prompt_example.txt`:
   - First paragraph: style + characters + set shared by the whole clip (locks consistency)
   - Then one line per shot, `Shot N:` with camera position (wide/close-up/medium) + action
   - Last line: the soundscape
The model cuts between shots on its own within a single generation (measured: clean cuts across 3 shots, no transition ghosting).

Measured (5090/nvfp4): 241 frames in ~155s, 1920×1088 + audio in one pass.
Best for: animatics and fast drafts. For finals, per-shot generation still gives more control.
