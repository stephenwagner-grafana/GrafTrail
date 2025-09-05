# GrafTrail

An always-on-top, click-through Windows overlay that draws a silky trail while you hold **Ctrl**.
- Smooth Catmull–Rom curves, glow + core stroke, rounded ends, bead-free joins
- Live settings (start/end colors, fade duration, thickness, smoothing)
- System tray with Pause, Run at startup, Settings, Quit

## Run from source
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python graftrail/app.py
