# WaveGlow 🌊

> Beautiful audio waveform visualizations with glow effects, transparent overlays, and plasma-style multi-line rendering.

Inspired by [seewav](https://github.com/adefossez/seewav) — built for content creators who need more visual control.

## Features

- 🎨 **Transparent background** — overlay directly onto any video
- ✨ **Glow effects** — multi-layer Gaussian blur for plasma/neon aesthetics  
- 〰️ **Multiple styles** — bars, plasma (multi-line sine waves), envelope
- 🎬 **Video overlay mode** — composite waveform onto existing video in one command
- 🎛️ **Full control** — colors, opacity, position, size, speed, reactivity

## Install

```bash
pip install waveglow
```

Or from source:
```bash
git clone https://github.com/hellojixian/waveglow
cd waveglow
pip install -e .
```

## Quick Start

```bash
# Overlay waveform onto a video
waveglow overlay audio.wav --video input.mp4 --output output.mp4

# Generate standalone waveform video (transparent bg)
waveglow render audio.wav --style plasma --output wave.mp4

# Bars style with custom color
waveglow render audio.wav --style bars --color 0.3,0.7,1.0 --glow 3
```

## Styles

| Style | Description |
|-------|-------------|
| `plasma` | Multi-line sine waves with glow, organic motion |
| `bars` | Scrolling bar graph with gradient fill |
| `envelope` | Classic seewav-style envelope bars |

## CLI Reference

```
waveglow render AUDIO [OPTIONS]
  --style        plasma|bars|envelope (default: plasma)
  --output       Output file (default: out.mp4)
  --width        Width in pixels (default: 1920)
  --height       Height in pixels (default: 200)
  --fps          Framerate (default: 30)
  --color        Primary color r,g,b in [0,1] (default: 0.3,0.7,1.0)
  --color2       Secondary color for gradient (default: 1.0,1.0,1.0)
  --glow         Glow intensity 0-10 (default: 5)
  --lines        Number of lines for plasma style (default: 8)
  --bars         Number of bars (default: 80)
  --speed        Animation speed (default: 4)
  --opacity      Overall opacity 0-1 (default: 1.0)
  --bg           Background color, 'transparent' or r,g,b (default: transparent)

waveglow overlay AUDIO [OPTIONS]
  --video        Input video to overlay onto (required)
  --output       Output file (default: out.mp4)
  --y            Vertical position from top (default: auto = bottom)
  --height       Waveform height (default: 200)
  + all render options
```

## Python API

```python
from waveglow import WaveGlow

wg = WaveGlow(style="plasma", color=(0.3, 0.7, 1.0), glow=5, lines=8)
wg.render("audio.wav", "wave.mp4", width=1920, height=200, transparent=True)
wg.overlay("audio.wav", "input.mp4", "output.mp4", y_position=880)
```

## License

MIT — free to use, modify, and distribute.
