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

    @staticmethod
    def _smoothstep(x):
        """Cubic smoothstep: 0→0, 1→1, with zero derivative at endpoints."""
        x = np.clip(x, 0.0, 1.0)
        return x * x * (3.0 - 2.0 * x)

    @staticmethod
    def _smootherstep(x):
        """Ken Perlin's quintic smoothstep: even smoother S-curve."""
        x = np.clip(x, 0.0, 1.0)
        return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)

    def _get_dist_x(self, W, H):
        """Elliptical arc distance field: bright on left/right arcs, fades at top/bottom corners."""
        if self._cache_shape != (W, H):
            # Normalised coords: cx in [-1, 1], cy in [-1, 1]
            cx = (np.arange(W, dtype=np.float32) / (W * 0.5) - 1.0)  # -1=left, 0=center, 1=right
            cy = (np.arange(H, dtype=np.float32) / (H * 0.5) - 1.0)  # -1=top,  0=center, 1=bottom
            CX, CY = np.meshgrid(cx, cy)  # (H, W)

            # For each pixel, distance to the nearest point on the unit ellipse (a=1, b=1).
            # Approximate: signed radial distance from unit circle edge = 1 - r, clamped.
            # Use a squashed ellipse: a=1.0 (width), b=0.85 (height) so arcs are tall but curve.
            a, b = 1.0, 0.85
            r = np.sqrt((CX / a) ** 2 + (CY / b) ** 2)  # 0=center, 1=ellipse edge

            # Distance FROM the ellipse boundary (positive outside, negative inside).
            # We want pixels OUTSIDE the ellipse (near the frame edges) to be bright.
            # dist_from_ellipse: 0 at ellipse, positive inward (toward center), positive outward.
            # For glow we care about: how close is this pixel to the ellipse?
            dist_from_ellipse = np.abs(r - 1.0)  # 0=on ellipse boundary

            # But we only want the left/right portions: weight by |CX| / r so top/bottom fade
            # (When r==0 use 0 to avoid div-by-zero)
            safe_r = np.where(r < 1e-6, 1e-6, r)
            side_weight = np.abs(CX) / safe_r  # 1=pure left/right, 0=pure top/bottom
            # Smooth the weight with smootherstep so corners taper off gracefully
            side_weight = self._smootherstep(side_weight)

            # Combined: distance in [0, +∞), small near the arc, weighted to zero at top/bottom
            # Normalise dist so that ~0.25 of frame width = 1.0
            self._dist_x_cache = dist_from_ellipse / (side_weight + 0.01)
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

        # Glow reach: how far inward the glow extends (fraction of half-width)
        reach = 0.30 + 0.20 * (self.glow_intensity / 10.0)  # 0.30–0.50

        # Map dist 0..reach → 1..0 using smootherstep for silky S-curve falloff
        t_dist = np.clip(dist_field / reach, 0.0, 1.0)  # 0=edge bright, 1=reach boundary
        glow_mask = self._smootherstep(1.0 - t_dist)     # 1 at edge, 0 at reach boundary

        # Final alpha
        alpha_arr = (glow_mask * frame_alpha * 255).clip(0, 255).astype(np.uint8)

        # Build RGBA
        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0] = cr
        rgba[:, :, 1] = cg
        rgba[:, :, 2] = cb
        rgba[:, :, 3] = alpha_arr

        return Image.fromarray(rgba, mode="RGBA")


class GlowWaveEdgeStyle:
    """
    Wave-edge glow: left and right edges emit a living, wavy glow.
    The edge boundary is NOT a straight line — it's a smoothly animated waveform
    driven by the audio signal.  Brightness range: 0%–8% (subtle, no harsh flashes).
    """

    def __init__(self, color=None, color2=None, glow=6, fps=30, **kwargs):
        self.color  = color  or (0.10, 0.23, 0.42)   # deep blue
        self.color2 = color2 or (0.30, 0.62, 1.00)   # bright blue
        self.glow_intensity = max(1, min(10, glow))
        self.fps = fps
        # EMA for overall amplitude
        tau = 0.4
        self._ema_alpha = 1.0 - math.exp(-1.0 / (fps * tau))
        self._smoothed_amp = 0.0
        # Wave phase accumulator — advances each frame for continuous motion
        self._phase = 0.0
        # Random frequency / amplitude seeds for multi-octave wave
        rng = np.random.default_rng(42)
        self._freqs  = rng.uniform(0.8, 3.5, size=5).astype(np.float32)   # spatial frequencies
        self._phases = rng.uniform(0, 2 * math.pi, size=5).astype(np.float32)  # initial offsets
        self._amps   = rng.uniform(0.3, 1.0, size=5).astype(np.float32)        # relative weights
        self._amps  /= self._amps.sum()  # normalise
        self._speeds = rng.uniform(0.4, 1.4, size=5).astype(np.float32)   # per-octave time speeds

    @staticmethod
    def _smootherstep(x):
        x = np.clip(x, 0.0, 1.0)
        return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)

    def render_frame(self, fi, amplitude, W, H, fps=30):
        # --- Smooth amplitude ---
        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp = self._smoothed_amp
        t_amp = min(amp * 2.5, 1.0)  # 0→1 response curve

        # --- Brightness: 0%–8% ---
        base_alpha = 0.00
        peak_alpha = 0.08
        frame_alpha = base_alpha + (peak_alpha - base_alpha) * t_amp

        # --- Color lerp ---
        r1, g1, b1 = self.color
        r2, g2, b2 = self.color2
        cr = int((r1 + (r2 - r1) * t_amp) * 255)
        cg = int((g1 + (g2 - g1) * t_amp) * 255)
        cb = int((b1 + (b2 - b1) * t_amp) * 255)

        # --- Compute wavy edge boundary (per row) ---
        # y_norm: 0=top, 1=bottom
        y_norm = np.linspace(0.0, 1.0, H, dtype=np.float32)
        t_time = fi / fps  # seconds elapsed

        # Multi-octave sine wave sum along Y axis
        wave = np.zeros(H, dtype=np.float32)
        for k in range(len(self._freqs)):
            phase_t = self._phases[k] + t_time * self._speeds[k] * 2.0 * math.pi
            wave += self._amps[k] * np.sin(self._freqs[k] * y_norm * 2.0 * math.pi + phase_t)
        # wave is in [-1, 1]; scale to pixel offset
        # Max edge displacement: 8% of half-width, modulated by amplitude
        max_disp_px = W * 0.08 * (0.3 + 0.7 * t_amp)  # more wavy when louder
        edge_disp = wave * max_disp_px  # (H,) pixel offset from the raw frame edge

        # Glow reach (inward from edge): 15%–30% of half-width
        reach_frac = 0.15 + 0.15 * (self.glow_intensity / 10.0)
        reach_px   = W * reach_frac

        # --- Build pixel distance field ---
        # x_idx: (W,) array of pixel x positions
        x_idx = np.arange(W, dtype=np.float32)  # 0=left, W-1=right

        # Left edge: wavy boundary at x = edge_disp[row] (from left)
        # dist_left[row, col] = max(0, col - boundary_left[row])
        boundary_left  = edge_disp          # (H,) — positive = boundary pushes inward
        boundary_right = (W - 1) - edge_disp  # (H,) — symmetric on the right

        # Broadcast: (H,1) vs (1,W)
        BL = boundary_left[:, np.newaxis]   # (H, 1)
        BR = boundary_right[:, np.newaxis]  # (H, 1)
        XI = x_idx[np.newaxis, :]           # (1, W)

        dist_left_arr  = np.maximum(0.0, XI - BL)          # 0 on/outside left boundary
        dist_right_arr = np.maximum(0.0, BR - XI)          # 0 on/outside right boundary (mirrored)
        # Wait — we want INSIDE distance (from boundary inward to center)
        # dist_left = how far pixel is from left wavy boundary (0 at boundary, grows inward)
        dist_left_from_boundary  = np.abs(XI - BL)  # closest distance to left edge curve
        dist_right_from_boundary = np.abs(XI - BR)  # closest distance to right edge curve
        dist_field = np.minimum(dist_left_from_boundary, dist_right_from_boundary)  # (H, W)

        # Normalise by reach_px and apply smootherstep
        t_dist = np.clip(dist_field / reach_px, 0.0, 1.0)
        glow_mask = self._smootherstep(1.0 - t_dist)  # bright near edge, fades inward

        # Final alpha
        alpha_arr = (glow_mask * frame_alpha * 255).clip(0, 255).astype(np.uint8)

        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0] = cr
        rgba[:, :, 1] = cg
        rgba[:, :, 2] = cb
        rgba[:, :, 3] = alpha_arr
        return Image.fromarray(rgba, mode="RGBA")


class GlowTopBottomStyle(GlowEdgeStyle):
    """
    Breathing glow from top and bottom edges only.
    Glow height is 40% of the original GlowEdgeStyle reach.
    """

    # Scale factor applied to reach so the glow band is narrower
    REACH_SCALE = 0.40

    def render_frame(self, fi, amplitude, W, H, fps=30):
        """Same as parent but reach scaled to 40%."""
        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp = self._smoothed_amp

        base_alpha = 0.02
        peak_alpha = 0.15
        t = min(amp * 2.0, 1.0)
        frame_alpha = base_alpha + (peak_alpha - base_alpha) * t

        r1, g1, b1 = self.color
        r2, g2, b2 = self.color2
        cr = int((r1 + (r2 - r1) * t) * 255)
        cg = int((g1 + (g2 - g1) * t) * 255)
        cb = int((b1 + (b2 - b1) * t) * 255)

        dist_field = self._get_dist_x(W, H)

        # reach at 40% of original
        reach = (0.30 + 0.20 * (self.glow_intensity / 10.0)) * self.REACH_SCALE

        t_dist = np.clip(dist_field / reach, 0.0, 1.0)
        glow_mask = self._smootherstep(1.0 - t_dist)

        alpha_arr = (glow_mask * frame_alpha * 255).clip(0, 255).astype(np.uint8)

        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0] = cr
        rgba[:, :, 1] = cg
        rgba[:, :, 2] = cb
        rgba[:, :, 3] = alpha_arr
        return Image.fromarray(rgba, mode="RGBA")

    def _get_dist_x(self, W, H):
        """Top-bottom distance field (reuses parent smootherstep + caching)."""
        if self._cache_shape != (W, H):
            y_idx = np.arange(H, dtype=np.float32)
            # Normalised distance from top/bottom edge: 0=edge, 1=center
            dist_top    = y_idx / (H * 0.5)
            dist_bottom = (H - 1 - y_idx) / (H * 0.5)
            dist_y = np.minimum(dist_top, dist_bottom)  # (H,)
            # Broadcast to (H, W)
            self._dist_x_cache = np.broadcast_to(dist_y[:, np.newaxis], (H, W)).copy()
            self._cache_shape = (W, H)
        return self._dist_x_cache


class GlowBottomWaveStyle:
    """
    Bottom-edge glow + plasma waveform overlay — GPU-accelerated via PyTorch CUDA.
    Falls back to CPU (numpy) if CUDA is unavailable.
    - Soft breathing gradient from the bottom edge upward (smootherstep, 40% height)
    - Multi-line plasma wave oscillating near the bottom edge
    - Brightness: 0%–15%
    """

    def __init__(self, color=None, color2=None, glow=6, fps=30, **kwargs):
        self.color  = color  or (0.10, 0.23, 0.42)
        self.color2 = color2 or (0.30, 0.62, 1.00)
        self.glow_intensity = max(1, min(10, glow))
        self.fps = fps
        tau = 0.4
        self._ema_alpha = 1.0 - math.exp(-1.0 / (fps * tau))
        self._smoothed_amp = 0.0
        self._cache_shape = None
        self._dist_cache = None   # GPU tensor when CUDA available

        # Detect GPU
        try:
            import torch
            self._torch = torch
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            # torch.compile available in PyTorch 2.0+ — reduces kernel launch overhead
            self._compile_available = hasattr(torch, 'compile') and self._device.type == "cuda"
        except ImportError:
            self._torch = None
            self._device = None
            self._compile_available = False

        # Wave parameters
        rng = np.random.default_rng(7)
        self._freqs  = rng.uniform(0.5, 2.5, size=5).astype(np.float32)
        self._phases = rng.uniform(0, 2 * math.pi, size=5).astype(np.float32)
        self._wamps  = rng.uniform(0.3, 1.0, size=5).astype(np.float32)
        self._wamps /= self._wamps.sum()
        self._speeds = rng.uniform(0.3, 1.0, size=5).astype(np.float32)
        self._n_lines = 6

        # Line configs: (y_base_frac_from_bottom, sigma_px, weight)
        # Near bottom edge
        self._line_cfgs = [
            (0.06, 3.0, 1.00),
            (0.06, 8.0, 0.40),
            (0.10, 2.0, 0.65),
            (0.10, 6.0, 0.25),
            (0.03, 1.5, 0.50),
            (0.13, 1.5, 0.30),
        ]

    def _get_dist_cache(self, W, H):
        """Top+bottom combined distance field: 0 at top/bottom edges, 1 at center."""
        if self._cache_shape != (W, H):
            if self._torch is not None:
                torch = self._torch
                y_idx = torch.arange(H, dtype=torch.float32, device=self._device)
                # 0=bottom edge, 1=top edge; take min(dist_bottom, dist_top)
                dist_bottom = (H - 1 - y_idx) / float(H - 1)   # 0=bottom, 1=top
                dist_top    = y_idx / float(H - 1)               # 0=top, 1=bottom
                dist_edge   = torch.minimum(dist_bottom, dist_top)  # 0=either edge
                self._dist_cache = dist_edge.unsqueeze(1).expand(H, W).contiguous()
            else:
                y_idx = np.arange(H, dtype=np.float32)
                dist_bottom = (H - 1 - y_idx) / float(H - 1)
                dist_top    = y_idx / float(H - 1)
                dist_edge   = np.minimum(dist_bottom, dist_top)
                self._dist_cache = np.broadcast_to(dist_edge[:, np.newaxis], (H, W)).copy()
            self._cache_shape = (W, H)
        return self._dist_cache

    def render_frame(self, fi, amplitude, W, H, fps=30, pcm_window=None):
        """Returns PIL Image (for compatibility) or raw bytes — see render_frame_bytes."""
        if self._torch is not None and self._device.type == "cuda":
            return self._render_gpu(fi, amplitude, W, H, fps, pcm_window)
        return self._render_cpu(fi, amplitude, W, H, fps, pcm_window)

    def render_frame_bytes(self, fi, amplitude, W, H, fps=30, pcm_window=None):
        """Like render_frame but returns raw RGBA bytes directly (zero-copy GPU path)."""
        if self._torch is not None and self._device.type == "cuda":
            return self._render_gpu_bytes(fi, amplitude, W, H, fps, pcm_window)
        frame = self._render_cpu(fi, amplitude, W, H, fps, pcm_window)
        return frame.tobytes()

    def _render_gpu(self, fi, amplitude, W, H, fps, pcm_window=None):
        torch = self._torch
        dev   = self._device

        # EMA smooth
        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp   = self._smoothed_amp
        t_amp = min(amp * 2.0, 1.0)

        frame_alpha = 0.08 * t_amp   # 0–8% (half of original 15%)

        # Color lerp
        r1,g1,b1 = self.color;  r2,g2,b2 = self.color2
        cr = (r1 + (r2-r1)*t_amp) * 255
        cg = (g1 + (g2-g1)*t_amp) * 255
        cb = (b1 + (b2-b1)*t_amp) * 255

        # ---- Layer 1: bottom glow gradient (GPU) ----
        dist_field = self._get_dist_cache(W, H)   # (H, W) GPU tensor, 0=bottom
        reach_base = (0.30 + 0.20 * (self.glow_intensity / 10.0)) * 0.40
        reach = reach_base * (0.3 + 0.7 * t_amp)   # dynamic height: quiet=30%, loud=100%
        t_dist = (dist_field / reach).clamp(0.0, 1.0)
        # smootherstep of (1 - t_dist)
        s = 1.0 - t_dist
        glow_mask  = s * s * s * (s * (s * 6.0 - 15.0) + 10.0)   # (H, W)
        alpha_glow = glow_mask * frame_alpha

        # ---- Layer 2: wave lines (GPU) ----
        t_time    = fi / fps
        # Amplitude drives oscillation height (0=flat line, 1=full swing)
        max_osc   = H * 0.09 * t_amp
        x_norm    = torch.linspace(0.0, 1.0, W, dtype=torch.float32, device=dev)  # (W,)
        y_idx_col = torch.arange(H, dtype=torch.float32, device=dev).unsqueeze(1)  # (H,1)

        wave_alpha_gpu = torch.zeros(H, W, dtype=torch.float32, device=dev)

        # All lines converge to center line when silent, spread apart with amplitude
        base_frac_center = self._line_cfgs[0][0]
        for k, (y_base_frac, sigma, weight) in enumerate(self._line_cfgs[:self._n_lines]):
            spread_frac = (y_base_frac - base_frac_center) * t_amp
            effective_frac = base_frac_center + spread_frac
            # V17 style: scrolling sine (t_time drives phase = horizontal scroll)
            wave_y = torch.zeros(W, dtype=torch.float32, device=dev)
            for i in range(len(self._freqs)):
                phase_t = float(self._phases[i]) + t_time * float(self._speeds[i]) * 2.0 * math.pi
                wave_y = wave_y + float(self._wamps[i]) * torch.sin(
                    float(self._freqs[i]) * x_norm * (2.0 * math.pi) + phase_t + k * 0.9
                )
            # Anchor row: distance from bottom, converted to pixel row
            base_row   = (H - 1) - effective_frac * H
            anchor_row = (base_row - wave_y * max_osc).clamp(0, H - 1)  # (W,)

            # Gaussian blob: (H,1) vs (1,W) broadcast
            dist_px   = (y_idx_col - anchor_row.unsqueeze(0)).abs()  # (H, W)
            line_mask = torch.exp(-0.5 * (dist_px / sigma) ** 2)
            wave_alpha_gpu = wave_alpha_gpu + line_mask * weight

        wave_alpha_gpu = wave_alpha_gpu.clamp(0.0, 1.0)
        # Wave always visible (base 0.2 alpha), amplitude drives extra brightness
        wave_frame_alpha = 0.2 + 0.2 * t_amp
        alpha_wave = wave_alpha_gpu * wave_frame_alpha

        # ---- Combine: single color (glow + wave share same color) ----
        alpha_combined = torch.maximum(alpha_glow, alpha_wave).clamp(0.0, 1.0)
        alpha_u8 = (alpha_combined * 255).to(torch.uint8)

        rgba_gpu = torch.zeros(H, W, 4, dtype=torch.uint8, device=dev)
        rgba_gpu[:, :, 0] = int(cr)
        rgba_gpu[:, :, 1] = int(cg)
        rgba_gpu[:, :, 2] = int(cb)
        rgba_gpu[:, :, 3] = alpha_u8

        rgba_np = rgba_gpu.cpu().numpy()
        return Image.fromarray(rgba_np, mode="RGBA")

    def _render_gpu_bytes(self, fi, amplitude, W, H, fps, pcm_window=None):
        """GPU-accelerated render — fully batched wave computation, zero-copy bytes output.

        Key optimization vs old version:
        - Old: 6 lines × 5 freqs = 30 sequential CUDA kernel launches (Python for-loops)
        - New: single batched matmul for all sin() calls → 1 kernel launch total
        """
        torch = self._torch
        dev   = self._device

        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp   = self._smoothed_amp
        t_amp = min(amp * 2.0, 1.0)

        frame_alpha = 0.08 * t_amp

        r1,g1,b1 = self.color;  r2,g2,b2 = self.color2
        cr = int((r1 + (r2-r1)*t_amp) * 255)
        cg = int((g1 + (g2-g1)*t_amp) * 255)
        cb = int((b1 + (b2-b1)*t_amp) * 255)

        # ---- Glow layer ----
        dist_field = self._get_dist_cache(W, H)
        reach_base = (0.30 + 0.20 * (self.glow_intensity / 10.0)) * 0.40
        reach = reach_base * (0.3 + 0.7 * t_amp)
        t_dist = (dist_field / reach).clamp(0.0, 1.0)
        s = 1.0 - t_dist
        glow_mask  = s * s * s * (s * (s * 6.0 - 15.0) + 10.0)
        alpha_glow = glow_mask * frame_alpha

        # ---- Wave layer — fully batched ----
        t_time  = fi / fps
        max_osc = H * 0.09 * t_amp

        # x_norm: (W,)  →  phases_t: (n_freqs,)  →  freq_x: (n_freqs, W)
        x_norm = torch.linspace(0.0, 1.0, W, dtype=torch.float32, device=dev)  # (W,)

        # Ensure freq/phase/speed/wamp tensors are on GPU (cached after first frame)
        if not hasattr(self, '_t_freqs') or self._t_freqs.device != dev:
            self._t_freqs  = torch.tensor(self._freqs,  dtype=torch.float32, device=dev)  # (F,)
            self._t_phases = torch.tensor(self._phases, dtype=torch.float32, device=dev)  # (F,)
            self._t_speeds = torch.tensor(self._speeds, dtype=torch.float32, device=dev)  # (F,)
            self._t_wamps  = torch.tensor(self._wamps,  dtype=torch.float32, device=dev)  # (F,)

        n_lines = self._n_lines
        n_freqs = len(self._freqs)
        base_frac_center = self._line_cfgs[0][0]

        # k_offsets: (K,1)  —  per-line phase offset
        k_idx = torch.arange(n_lines, dtype=torch.float32, device=dev)  # (K,)
        k_offset = k_idx * 0.9  # (K,)

        # phase_t: (F,)  — current scroll phase per frequency
        phase_t = self._t_phases + t_time * self._t_speeds * (2.0 * math.pi)  # (F,)

        # Batched sin: args shape (K, F, W)
        #   freq (F,) × x_norm (W,) → (F, W) → unsqueeze → (1, F, W)
        #   phase_t (F,) → (1, F, 1)
        #   k_offset (K,) → (K, 1, 1)
        freq_x  = self._t_freqs.unsqueeze(1) * x_norm.unsqueeze(0) * (2.0 * math.pi)  # (F, W)
        args    = freq_x.unsqueeze(0) + phase_t.view(1, n_freqs, 1) + k_offset.view(n_lines, 1, 1)  # (K,F,W)
        sins    = torch.sin(args)  # (K, F, W)  — single fused kernel

        # Weighted sum over freqs: wave_y_per_line (K, W)
        wave_y_lines = (sins * self._t_wamps.view(1, n_freqs, 1)).sum(dim=1)  # (K, W)

        # Per-line effective anchor rows: (K, W)
        y_idx_col = torch.arange(H, dtype=torch.float32, device=dev).view(H, 1, 1)  # (H,1,1)

        # Precompute per-line base_rows and sigmas/weights as tensors
        if not hasattr(self, '_t_line_base_rows') or self._t_line_base_rows.shape[0] != n_lines:
            eff_fracs  = torch.tensor(
                [base_frac_center + (cfg[0] - base_frac_center) for cfg in self._line_cfgs[:n_lines]],
                dtype=torch.float32, device=dev)                                     # (K,)
            self._t_eff_fracs_base = eff_fracs  # store base; spread applied per frame
            self._t_sigmas  = torch.tensor([cfg[1] for cfg in self._line_cfgs[:n_lines]], dtype=torch.float32, device=dev)  # (K,)
            self._t_weights = torch.tensor([cfg[2] for cfg in self._line_cfgs[:n_lines]], dtype=torch.float32, device=dev)  # (K,)
            self._t_ybase_fracs = torch.tensor([cfg[0] for cfg in self._line_cfgs[:n_lines]], dtype=torch.float32, device=dev)

        # Spread lines apart with amplitude
        spread_fracs   = base_frac_center + (self._t_ybase_fracs - base_frac_center) * t_amp  # (K,)
        base_rows      = (H - 1) - spread_fracs * H                                            # (K,)
        anchor_rows    = (base_rows.view(n_lines, 1) - wave_y_lines * max_osc).clamp(0, H-1)  # (K, W)

        # Gaussian distance: (H, K, W) via broadcasting
        dist_px   = (y_idx_col - anchor_rows.unsqueeze(0)).abs()           # (H, K, W)
        sigmas    = self._t_sigmas.view(1, n_lines, 1)                     # (1, K, 1)
        line_mask = torch.exp(-0.5 * (dist_px / sigmas) ** 2)             # (H, K, W)
        weights   = self._t_weights.view(1, n_lines, 1)                    # (1, K, 1)

        wave_alpha_gpu = (line_mask * weights).sum(dim=1).clamp(0.0, 1.0)  # (H, W)

        wave_frame_alpha = 0.2 + 0.2 * t_amp
        alpha_wave = wave_alpha_gpu * wave_frame_alpha

        # ---- Combine & output ----
        alpha_combined = torch.maximum(alpha_glow, alpha_wave).clamp(0.0, 1.0)
        alpha_u8 = (alpha_combined * 255).to(torch.uint8)  # (H, W)

        # Build RGBA in a single stacked op (no scalar fill loops)
        color_plane = torch.tensor([cr, cg, cb], dtype=torch.uint8, device=dev)  # (3,)
        rgb_planes  = color_plane.view(1, 1, 3).expand(H, W, 3)                  # (H, W, 3)
        rgba_gpu    = torch.cat([rgb_planes, alpha_u8.unsqueeze(2)], dim=2)       # (H, W, 4)

        # ✅ Zero-copy: contiguous GPU tensor → single CPU transfer → raw bytes
        return rgba_gpu.contiguous().cpu().numpy().tobytes()

    def _render_cpu(self, fi, amplitude, W, H, fps, pcm_window=None):
        """CPU fallback (numpy) — identical logic, no torch dependency."""
        self._smoothed_amp += self._ema_alpha * (amplitude - self._smoothed_amp)
        amp   = self._smoothed_amp
        t_amp = min(amp * 2.0, 1.0)
        frame_alpha = 0.15 * t_amp

        r1,g1,b1 = self.color;  r2,g2,b2 = self.color2
        cr = int((r1 + (r2-r1)*t_amp) * 255)
        cg = int((g1 + (g2-g1)*t_amp) * 255)
        cb = int((b1 + (b2-b1)*t_amp) * 255)

        dist_field = self._get_dist_cache(W, H)
        reach_base = (0.30 + 0.20 * (self.glow_intensity / 10.0)) * 0.40
        reach = reach_base * (0.3 + 0.7 * t_amp)
        t_dist = np.clip(dist_field / reach, 0.0, 1.0)
        s = 1.0 - t_dist
        glow_mask  = s*s*s*(s*(s*6.0-15.0)+10.0)
        alpha_glow = glow_mask * frame_alpha

        t_time   = fi / fps
        max_osc  = H * 0.09 * t_amp  # amplitude drives oscillation; 0=flat line
        x_norm   = np.linspace(0.0, 1.0, W, dtype=np.float32)
        y_idx    = np.arange(H, dtype=np.float32)[:, np.newaxis]
        wave_alpha = np.zeros((H, W), dtype=np.float32)

        base_frac_center = self._line_cfgs[0][0]
        for k, (y_base_frac, sigma, weight) in enumerate(self._line_cfgs[:self._n_lines]):
            spread_frac = (y_base_frac - base_frac_center) * t_amp
            effective_frac = base_frac_center + spread_frac
            wave_y = np.zeros(W, dtype=np.float32)
            for i in range(len(self._freqs)):
                phase_t = self._phases[i] + t_time * self._speeds[i] * 2.0 * math.pi
                wave_y += self._wamps[i] * np.sin(
                    self._freqs[i] * x_norm * 2.0 * math.pi + phase_t + k * 0.9
                )
            base_row   = (H - 1) - effective_frac * H
            anchor_row = np.clip(base_row - wave_y * max_osc, 0, H - 1)
            dist_px    = np.abs(y_idx - anchor_row[np.newaxis, :])
            wave_alpha += np.exp(-0.5 * (dist_px / sigma) ** 2) * weight

        wave_alpha = np.clip(wave_alpha, 0.0, 1.0)
        wave_frame_alpha = 0.4 + 0.4 * t_amp  # always visible; louder = brighter
        alpha_wave = wave_alpha * wave_frame_alpha

        alpha_combined = np.clip(np.maximum(alpha_glow, alpha_wave), 0.0, 1.0)
        alpha_arr = (alpha_combined * 255).astype(np.uint8)

        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:,:,0] = cr;  rgba[:,:,1] = cg;  rgba[:,:,2] = cb;  rgba[:,:,3] = alpha_arr
        return Image.fromarray(rgba, mode="RGBA")
