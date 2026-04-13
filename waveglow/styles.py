"""
WaveGlow rendering styles.
Each style implements render_frame(frame_idx, amplitude, audio_data, config) -> PIL.Image (RGBA)
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# Gradient color stops: (position 0-1, R, G, B) along x-axis per line type
# Each line type has its own gradient palette for visual layering
LINE_GRADIENTS = [
    # core: white → ice blue → bright blue
    [(0.0, 255, 255, 255), (0.3, 200, 225, 255), (0.6, 120, 185, 255), (1.0, 77, 158, 255)],
    # near-white: same but slightly dimmer
    [(0.0, 220, 235, 255), (0.4, 160, 200, 255), (0.8, 90, 160, 255), (1.0, 60, 120, 230)],
    # bright blue
    [(0.0, 150, 200, 255), (0.35, 77, 158, 255), (0.7, 50, 110, 220), (1.0, 30, 80, 190)],
    # blue
    [(0.0, 100, 160, 240), (0.4, 60, 120, 210), (0.8, 35, 85, 175), (1.0, 20, 60, 150)],
    # mid blue
    [(0.0, 80, 130, 210), (0.5, 45, 90, 180), (1.0, 20, 55, 140)],
    # deep blue
    [(0.0, 55, 100, 190), (0.5, 30, 70, 155), (1.0, 15, 45, 120)],
    # deeper blue
    [(0.0, 40, 80, 165), (0.5, 20, 55, 130), (1.0, 10, 35, 100)],
    # navy
    [(0.0, 25, 60, 140), (0.5, 15, 40, 110), (1.0, 8, 25, 80)],
]


def _interp_gradient(stops, t):
    """Linear interpolation across gradient stops. t in [0,1]."""
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        p0, *c0 = stops[i]
        p1, *c1 = stops[i + 1]
        if p0 <= t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0
            return tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return tuple(stops[-1][1:])


class PlasmaStyle:
    """
    Multi-line sine wave overlay with glow — organic plasma/neon aesthetic.
    Features:
    - Dynamic line width that breathes with amplitude and position
    - Per-segment x-axis gradient color (white core → blue edge)
    - Multi-layer glow blur
    - Independent phase/freq per line for organic motion
    """

    DEFAULT_LINE_CONFIGS = [
        # (base_alpha, phase, freq_mult, amp_mult, base_width, gradient_idx)
        (1.00,  0.00,  1.00,  1.00,  3.5, 0),  # white core — thickest
        (0.85,  0.08,  1.02,  0.97,  2.5, 1),  # near-white
        (0.90, -0.10,  0.98,  0.93,  2.0, 2),  # bright blue
        (0.80,  0.18,  1.06,  0.88,  1.8, 3),  # blue
        (0.70, -0.25,  0.92,  0.82,  1.5, 4),  # mid blue
        (0.60,  0.40,  1.12,  0.75,  1.3, 5),  # deep blue
        (0.50, -0.45,  0.82,  0.68,  1.0, 6),  # deeper blue
        (0.35,  0.65,  1.20,  0.60,  1.0, 7),  # navy — thinnest
    ]

    def __init__(self, color=None, color2=None, glow=5, lines=8):
        self.glow = glow
        self.lines = min(lines, len(self.DEFAULT_LINE_CONFIGS))
        self.line_configs = list(self.DEFAULT_LINE_CONFIGS[:self.lines])
        self._custom_gradient = None
        if color:
            # Build custom gradient from provided color
            r, g, b = [int(c * 255) for c in color]
            r2, g2, b2 = [int(c * 255) for c in (color2 or (1.0, 1.0, 1.0))]
            self._custom_gradient = [
                (0.0, r2, g2, b2),
                (0.4, int(r2*.7+r*.3), int(g2*.7+g*.3), int(b2*.7+b*.3)),
                (0.75, r, g, b),
                (1.0, int(r*0.55), int(g*0.55), int(b*0.55)),
            ]

    def _get_color(self, grad_idx, x_pos):
        """Return (R, G, B) for a given gradient and x position [0,1]."""
        stops = self._custom_gradient if self._custom_gradient else LINE_GRADIENTS[grad_idx % len(LINE_GRADIENTS)]
        return _interp_gradient(stops, x_pos)

    def _dynamic_width(self, base_w, x_pos, t, amplitude, line_idx):
        """
        Compute line width at position x_pos with breathing animation.
        Width peaks near center, pulses with amplitude, and has per-line oscillation.
        """
        # Center bulge: thicker in the middle, thinner at edges
        center_envelope = math.sin(x_pos * math.pi) ** 0.6  # [0..1]
        # Breathing oscillation (each line at different phase)
        breath = 0.5 + 0.5 * math.sin(t * 1.8 + line_idx * 0.9)
        # Amplitude reactivity
        amp_boost = 1.0 + amplitude * 1.5
        # Combine — minimum 1px so line never disappears during silence
        w = base_w * center_envelope * amp_boost * (0.7 + 0.3 * breath)
        return max(1, int(round(w)))

    def render_frame(self, fi, amplitude, W, H, fps=30):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        t = fi * 0.09
        wave_h = H * 0.40
        cy = H // 2

        def wave_y(x, phase, freq, amp_mult):
            tx = x / W
            edge = min(tx * 5, (1 - tx) * 5, 1.0)
            # amplitude=0 → flat line at center; amplitude>0 → full wave
            eff_amp = amplitude * amp_mult
            y = (
                math.sin(tx * math.pi * 3.5 * freq + t + phase) * 0.50 +
                math.sin(tx * math.pi * 7.1 * freq + t * 1.4 + phase * 2.1) * 0.28 +
                math.sin(tx * math.pi * 1.8 * freq + t * 0.6 + phase * 0.7) * 0.22
            )
            return int(cy + y * wave_h * eff_amp * edge)

        glow_scales = self._glow_layers(self.glow)
        step = 3  # x pixel step — balance quality vs speed

        for line_idx, (base_alpha, phase, freq, amp_mult, base_w, grad_idx) in enumerate(reversed(self.line_configs)):
            real_idx = (self.lines - 1) - line_idx  # original index for gradient

            pts = []
            for x in range(0, W, step):
                y = wave_y(x, phase, freq, amplitude * amp_mult)
                y = max(1, min(H - 2, y))
                pts.append((x, y))

            # Keep a minimum alpha so lines stay visible during silence
            # Overall brightness reduced to 45% — subtle, non-distracting
            brightness = 0.45
            min_alpha = int(255 * base_alpha * 0.12 * brightness)
            effective_alpha = max(min_alpha, int(255 * base_alpha * brightness * min(amplitude * 1.8, 1.0)))

            for blur_r, a_mult in glow_scales:
                a = min(int(effective_alpha * a_mult), 255)
                if a < 4:
                    continue
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(layer)

                for i in range(len(pts) - 1):
                    x0, y0 = pts[i]
                    x1, y1 = pts[i + 1]
                    x_pos = x0 / W  # normalized x position [0, 1]

                    # Dynamic width at this position
                    w = self._dynamic_width(base_w, x_pos, t, amplitude, real_idx)
                    # Gradient color at this x position
                    r, g, b = self._get_color(real_idx if not self._custom_gradient else 0, x_pos)

                    draw.line([(x0, y0), (x1, y1)], fill=(r, g, b, a), width=w)

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


class GlowEdgeStyle:
    """
    Breathing side-glow effect: left and right edges only, inward gradient.
    - Max brightness capped at 15%
    - Amplitude smoothed with EMA (~0.5s lag) for gentle breathing, not instant jumps
    """

    def __init__(self, color=None, color2=None, glow=6, fps=30, **kwargs):
        # Primary glow color (default: deep blue #1A3A6A)
        self.color = color or (0.10, 0.23, 0.42)
        # Accent color for peak brightness (default: bright blue #4D9EFF)
        self.color2 = color2 or (0.30, 0.62, 1.00)
        self.glow_intensity = max(1, min(10, glow))
        # EMA smoothing: alpha = 1 - e^(-1/(fps*tau)) where tau is time constant in seconds
        # tau=0.5s at 30fps → smooth transitions ~15 frames
        tau = 0.5  # seconds
        self._ema_alpha = 1.0 - math.exp(-1.0 / (fps * tau))
        self._smoothed_amp = 0.0
        # Pre-compute static gradient mask (only depends on W, H)
        self._cache_shape = None
        self._dist_x_cache = None

    def _get_dist_x(self, W, H):
        """Left-right only distance field, cached per resolution."""
        if self._cache_shape != (W, H):
            x_idx = np.arange(W, dtype=np.float32)
            # Normalized distance from left/right edge: 0=edge, 1=center
            dist_left  = x_idx / (W * 0.5)
            dist_right = (W - 1 - x_idx) / (W * 0.5)
            dist_x = np.minimum(dist_left, dist_right)  # (W,)
            # Broadcast to (H, W)
            self._dist_x_cache = np.broadcast_to(dist_x[np.newaxis, :], (H, W)).copy()
            self._cache_shape = (W, H)
        return self._dist_x_cache

    def render_frame(self, fi, amplitude, W, H, fps=30):
        """
        Render a full-frame RGBA side glow (left + right only).
        amplitude: 0.0–1.0 (audio RMS, raw)
        """
        # --- Smooth amplitude with EMA ---
        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp = self._smoothed_amp

        # --- Brightness: base 2%, peak hard-capped at 15% ---
        base_alpha  = 0.02
        peak_alpha  = 0.15
        t = min(amp * 2.0, 1.0)  # map 0–0.5 RMS to 0–1
        frame_alpha = base_alpha + (peak_alpha - base_alpha) * t  # 0.02–0.15

        # --- Color: lerp base → accent ---
        r1, g1, b1 = self.color
        r2, g2, b2 = self.color2
        cr = int((r1 + (r2 - r1) * t) * 255)
        cg = int((g1 + (g2 - g1) * t) * 255)
        cb = int((b1 + (b2 - b1) * t) * 255)

        # --- Spatial gradient: only left/right edges ---
        dist_field = self._get_dist_x(W, H)  # 0=edge, 1+=center

        # Glow falloff power: tighter glow at higher intensity
        glow_power = 2.0 - 0.8 * (self.glow_intensity / 10.0)  # 1.2–2.0
        glow_mask = np.clip(1.0 - dist_field ** glow_power, 0.0, 1.0)

        # Inner fade: limit glow reach to ~30% of half-width from each edge
        inner_fade_radius = 0.28 + 0.15 * (self.glow_intensity / 10.0)  # 0.28–0.43
        fade = np.clip(1.0 - dist_field / inner_fade_radius, 0.0, 1.0)
        glow_mask = glow_mask * fade

        # Final alpha
        alpha_arr = (glow_mask * frame_alpha * 255).clip(0, 255).astype(np.uint8)

        # Build RGBA
        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0] = cr
        rgba[:, :, 1] = cg
        rgba[:, :, 2] = cb
        rgba[:, :, 3] = alpha_arr

        return Image.fromarray(rgba, mode="RGBA")
