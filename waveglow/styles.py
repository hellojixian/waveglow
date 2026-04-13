"""
WaveGlow rendering styles.
Each style implements render_frame(frame_idx, amplitude, audio_data, config) -> PIL.Image (RGBA)
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


class PlasmaStyle:
    """
    Multi-line sine wave overlay with glow — organic plasma/neon aesthetic.
    """

    DEFAULT_LINE_CONFIGS = [
        # (color_rgb_01, base_alpha, phase, freq_mult, amp_mult)
        ((1.0, 1.0, 1.0),   1.00,  0.00,  1.00,  1.00),  # white core
        ((0.86, 0.92, 1.0), 0.85,  0.08,  1.02,  0.97),  # near-white
        ((0.47, 0.71, 1.0), 0.90,  -0.10, 0.98,  0.93),  # bright blue
        ((0.31, 0.59, 1.0), 0.80,  0.18,  1.06,  0.88),  # blue
        ((0.24, 0.47, 0.94),0.70,  -0.25, 0.92,  0.82),  # mid blue
        ((0.16, 0.35, 0.82),0.60,  0.40,  1.12,  0.75),  # deep blue
        ((0.08, 0.24, 0.71),0.50,  -0.45, 0.82,  0.68),  # deeper blue
        ((0.04, 0.16, 0.59),0.35,  0.65,  1.20,  0.60),  # navy
    ]

    def __init__(self, color=None, color2=None, glow=5, lines=8):
        self.glow = glow
        self.lines = min(lines, len(self.DEFAULT_LINE_CONFIGS))
        self.line_configs = self.DEFAULT_LINE_CONFIGS[:self.lines]
        # color overrides primary and secondary
        if color:
            r, g, b = color
            self.line_configs[0] = ((1.0, 1.0, 1.0), 1.00, 0.00, 1.00, 1.00)
            if self.lines > 1:
                self.line_configs[2] = ((r, g, b), 0.90, -0.10, 0.98, 0.93)

    def render_frame(self, fi, amplitude, W, H, fps=30):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        t = fi * 0.09
        wave_h = H * 0.40
        cx = W // 2
        cy = H // 2

        def wave_y(x, phase, freq, amp):
            tx = x / W
            edge = min(tx * 5, (1 - tx) * 5, 1.0)
            y = (
                math.sin(tx * math.pi * 3.5 * freq + t + phase) * 0.50 +
                math.sin(tx * math.pi * 7.1 * freq + t * 1.4 + phase * 2.1) * 0.28 +
                math.sin(tx * math.pi * 1.8 * freq + t * 0.6 + phase * 0.7) * 0.22
            )
            return int(cy + y * wave_h * amp * edge)

        glow_scales = self._glow_layers(self.glow)

        for color, base_alpha, phase, freq, amp in reversed(self.line_configs):
            pts = []
            for x in range(0, W, 2):
                y = wave_y(x, phase, freq, amplitude)
                y = max(1, min(H - 2, y))
                pts.append((x, y))

            effective_alpha = int(255 * base_alpha * min(amplitude * 1.8, 1.0))
            r, g, b = [int(c * 255) for c in color]

            for blur_r, a_mult in glow_scales:
                a = min(int(effective_alpha * a_mult), 255)
                if a < 4:
                    continue
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(layer)
                for i in range(len(pts) - 1):
                    draw.line([pts[i], pts[i + 1]], fill=(r, g, b, a), width=2)
                if blur_r > 0:
                    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur_r))
                img.alpha_composite(layer)

        return img

    def _glow_layers(self, glow_intensity):
        """Return list of (blur_radius, alpha_mult) based on glow intensity 0-10."""
        g = glow_intensity
        return [
            (0,           1.0),
            (max(1, g),   0.70),
            (max(3, g*2), 0.40),
            (max(8, g*4), 0.20),
            (max(20, g*8),0.10),
        ]


class BarsStyle:
    """
    Frequency bars with vertical gradient fill (top bright, bottom transparent).
    Uses FFT data for reactive frequency display.
    """

    def __init__(self, color=None, color2=None, glow=2, bars=80):
        self.bars = bars
        self.glow = glow
        self.color = color or (0.3, 0.7, 1.0)
        self.color2 = color2 or (1.0, 1.0, 1.0)  # top color

    def render_frame(self, fi, fft_frame, W, H, fps=30):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        n_bars = len(fft_frame)
        bar_w = max(1, (W - (n_bars - 1) * 2) // n_bars)
        gap = 2

        r1, g1, b1 = [int(c * 255) for c in self.color]
        r2, g2, b2 = [int(c * 255) for c in self.color2]

        for i, val in enumerate(fft_frame):
            bar_h = int(val * H * 0.92)
            if bar_h < 2:
                continue
            x = i * (bar_w + gap)
            for py in range(bar_h):
                t = py / max(bar_h - 1, 1)  # 0=bottom, 1=top
                r = int(r1 + (r2 - r1) * t)
                g = int(g1 + (g2 - g1) * t)
                b = int(b1 + (b2 - b1) * t)
                a = int(30 + (230 - 30) * t)
                y = H - 1 - py
                draw.line([(x, y), (x + bar_w - 1, y)], fill=(r, g, b, a))

        if self.glow > 0:
            blurred = img.filter(ImageFilter.GaussianBlur(radius=self.glow * 2))
            result = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            result.alpha_composite(blurred)
            result.alpha_composite(img)
            return result

        return img


class EnvelopeStyle:
    """
    Classic seewav-style envelope bars — scrolling window, sigmoid-compressed.
    Adapted from seewav (public domain) by Alexandre Défossez.
    """

    def __init__(self, color=None, color2=None, glow=1, bars=80, speed=4, time=0.4, oversample=4):
        self.bars = bars
        self.speed = speed
        self.time = time
        self.oversample = oversample
        self.glow = glow
        self.color = color or (0.3, 0.7, 1.0)

    def render_frame(self, fi, env, W, H, fps=30):
        """env: pre-computed envelope array (see audio.get_envelope)"""
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        smooth = np.hanning(self.bars)
        pos = fi * 1.0
        off = int(pos)
        loc = pos - off

        env1 = env[off * self.bars:(off + 1) * self.bars]
        env2 = env[(off + 1) * self.bars:(off + 2) * self.bars]
        if len(env1) < self.bars or len(env2) < self.bars:
            return img

        from .audio import sigmoid
        maxvol = math.log10(1e-4 + env2.max()) * 10
        speedup = np.clip(-6 + (0 - (-6)) * (maxvol - (-6)) / (0 - (-6)), 0.5, 2) if maxvol > -6 else 0.5
        w = sigmoid(self.speed * speedup * (loc - 0.5))
        denv = ((1 - w) * env1 + w * env2) * smooth

        pad_ratio = 0.1
        width = 1.0 / (self.bars * (1 + 2 * pad_ratio))
        pad = pad_ratio * width
        delta = 2 * pad + width
        bar_px = max(1, int(width * W))
        r, g, b = [int(c * 255) for c in self.color]

        for step in range(self.bars):
            half = int(denv[step] * H * 0.45)
            x = int((pad + step * delta) * W)
            cy = H // 2
            if half > 0:
                draw.rectangle([x, cy - half, x + bar_px, cy + half], fill=(r, g, b, 200))

        if self.glow > 0:
            blurred = img.filter(ImageFilter.GaussianBlur(radius=self.glow * 3))
            result = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            result.alpha_composite(blurred)
            result.alpha_composite(img)
            return result

        return img
