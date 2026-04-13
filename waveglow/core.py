"""
WaveGlow core — orchestrates audio loading, frame generation, and video compositing.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

from .audio import read_audio, get_rms_per_frame, get_fft_per_frame, get_envelope
from .styles import PlasmaStyle, BarsStyle, EnvelopeStyle, GlowEdgeStyle, GlowTopBottomStyle, GlowWaveEdgeStyle, GlowBottomWaveStyle


STYLES = {
    "plasma": PlasmaStyle,
    "bars": BarsStyle,
    "envelope": EnvelopeStyle,
    "glow-edge": GlowEdgeStyle,
    "glow-top-bottom": GlowTopBottomStyle,
    "glow-wave": GlowWaveEdgeStyle,
    "glow-bottom-wave": GlowBottomWaveStyle,
}


class WaveGlow:
    """
    Main WaveGlow class.

    Args:
        style: 'plasma' | 'bars' | 'envelope'
        color: primary color as (r, g, b) in [0, 1]
        color2: secondary color as (r, g, b) in [0, 1]
        glow: glow intensity 0-10 (default 5)
        lines: number of plasma lines (plasma style only)
        bars: number of bars (bars/envelope style)
        speed: animation speed (envelope style)
        opacity: overall opacity multiplier 0-1
        fps: output framerate
    """

    def __init__(
        self,
        style="plasma",
        color=None,
        color2=None,
        glow=5,
        lines=8,
        bars=80,
        speed=4,
        opacity=1.0,
        fps=30,
    ):
        self.fps = fps
        self.opacity = opacity
        self.style_name = style

        style_cls = STYLES.get(style, PlasmaStyle)
        self.renderer = style_cls(
            color=color,
            color2=color2,
            glow=glow,
            **({} if style == "envelope" else {}),
        )
        if style == "plasma":
            self.renderer = PlasmaStyle(color=color, color2=color2, glow=glow, lines=lines)
        elif style == "bars":
            self.renderer = BarsStyle(color=color, color2=color2, glow=glow, bars=bars)
        elif style == "envelope":
            self.renderer = EnvelopeStyle(color=color, color2=color2, glow=glow, bars=bars, speed=speed)
        elif style == "glow-edge":
            self.renderer = GlowEdgeStyle(color=color, color2=color2, glow=glow)
        elif style == "glow-top-bottom":
            self.renderer = GlowTopBottomStyle(color=color, color2=color2, glow=glow)
        elif style == "glow-wave":
            self.renderer = GlowWaveEdgeStyle(color=color, color2=color2, glow=glow)
        elif style == "glow-bottom-wave":
            self.renderer = GlowBottomWaveStyle(color=color, color2=color2, glow=glow)

    def render(self, audio_path, output_path, width=1920, height=200, bg=None, seek=None, duration=None):
        """
        Generate waveform video (transparent bg by default).

        Args:
            audio_path: path to audio file
            output_path: path for output .mp4
            width, height: dimensions of waveform area
            bg: background color (r,g,b) or None for transparent
            seek: start time in seconds
            duration: duration in seconds
        """
        audio_path = Path(audio_path)
        output_path = Path(output_path)

        wav, sr = read_audio(audio_path, seek=seek, duration=duration)
        n_frames = int(len(wav) / sr * self.fps)

        # Pre-compute audio data
        rms = get_rms_per_frame(wav, sr, fps=self.fps)
        fft = get_fft_per_frame(wav, sr, fps=self.fps)

        if self.style_name == "envelope":
            env = get_envelope(wav, sr)
            env = np.pad(env, (0, n_frames * 3))  # pad for safety

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            print(f"Rendering {n_frames} frames ({self.style_name} style)...")

            for fi in tqdm(range(n_frames), unit=" frames", ncols=80):
                amp = float(rms[fi]) if fi < len(rms) else 0.0
                amp = min(amp * 2.0, 1.0)  # boost reactivity

                if self.style_name == "plasma":
                    frame = self.renderer.render_frame(fi, amp, width, height, self.fps)
                elif self.style_name == "bars":
                    fft_frame = fft[fi] if fi < len(fft) else np.zeros(80)
                    frame = self.renderer.render_frame(fi, fft_frame, width, height, self.fps)
                elif self.style_name == "envelope":
                    frame = self.renderer.render_frame(fi, env, width, height, self.fps)
                else:
                    frame = self.renderer.render_frame(fi, amp, width, height, self.fps)

                # Apply opacity
                if self.opacity < 1.0:
                    r, g, b, a = frame.split()
                    a = a.point(lambda x: int(x * self.opacity))
                    frame = Image.merge("RGBA", (r, g, b, a))

                # Apply background
                if bg is not None:
                    bg_img = Image.new("RGBA", (width, height),
                                      (int(bg[0]*255), int(bg[1]*255), int(bg[2]*255), 255))
                    bg_img.alpha_composite(frame)
                    frame = bg_img

                frame.save(tmp / f"{fi:06d}.png")

            print("Encoding video...")
            audio_args = []
            if seek is not None:
                audio_args += ["-ss", str(seek)]
            audio_args += ["-i", str(audio_path.resolve())]
            if duration is not None:
                audio_args += ["-t", str(duration)]

            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "warning",
                "-framerate", str(self.fps),
                "-i", str(tmp / "%06d.png"),
            ] + audio_args + [
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuva420p" if bg is None else "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                str(output_path.resolve()),
            ], check=True, cwd=tmp)

        print(f"✓ Rendered: {output_path}")

    def overlay(self, audio_path, video_path, output_path, y_position=None,
                width=1920, height=200, seek=None, duration=None):
        """
        Composite waveform onto an existing video.

        Args:
            audio_path: audio file for waveform data
            video_path: input video to overlay on
            output_path: output file
            y_position: vertical position from top (None = bottom)
            width, height: waveform dimensions
        """
        audio_path = Path(audio_path)
        video_path = Path(video_path)
        output_path = Path(output_path)

        wav, sr = read_audio(audio_path, seek=seek, duration=duration)
        n_frames = int(len(wav) / sr * self.fps)

        rms = get_rms_per_frame(wav, sr, fps=self.fps)
        fft = get_fft_per_frame(wav, sr, fps=self.fps)

        if self.style_name == "envelope":
            env = get_envelope(wav, sr)
            env = np.pad(env, (0, n_frames * 3))

        # Detect video dimensions
        import json
        proc = subprocess.run([
            'ffprobe', "-loglevel", "panic",
            str(video_path), '-print_format', 'json', '-show_streams'
        ], capture_output=True)
        info = json.loads(proc.stdout.decode('utf-8'))
        vid_w = next((s['width']  for s in info['streams'] if s.get('codec_type') == 'video'), 1920)
        vid_h = next((s['height'] for s in info['streams'] if s.get('codec_type') == 'video'), 1080)

        # glow-edge / glow-top-bottom: full-frame overlay at (0,0) matching video size
        if self.style_name in ("glow-edge", "glow-top-bottom", "glow-wave", "glow-bottom-wave"):
            width = vid_w
            height = vid_h
            y_position = 0
        elif y_position is None:
            y_position = vid_h - height

        # Detect GPU encoder availability
        use_nvenc = self._nvenc_available()
        enc_args = (
            ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-pix_fmt", "yuv420p"]
            if use_nvenc else
            ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]
        )
        if use_nvenc:
            print("GPU encoding: h264_nvenc (RTX)")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            local_out = tmp / "output.mp4"

            print(f"Rendering {n_frames} frames (pipe to ffmpeg)...")

            # ffmpeg overlay pipeline: reads video + raw RGBA pipe, composites, encodes
            ff_cmd = [
                "ffmpeg", "-y", "-loglevel", "warning",
                "-i", str(video_path.resolve()),
                # raw RGBA frames pipe
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{width}x{height}",
                "-pix_fmt", "rgba",
                "-r", str(self.fps),
                "-i", "pipe:0",
                # audio
                "-i", str(audio_path.resolve()),
                "-filter_complex",
                f"[1:v]format=rgba[wv];[0:v][wv]overlay=0:{y_position}:format=auto[outv]",
                "-map", "[outv]", "-map", "2:a",
            ] + enc_args + [
                "-c:a", "aac", "-ar", "44100",
                str(local_out),
            ]

            ff_proc = subprocess.Popen(ff_cmd, stdin=subprocess.PIPE)

            for fi in tqdm(range(n_frames), unit=" frames", ncols=80):
                amp = float(rms[fi]) if fi < len(rms) else 0.0
                amp = min(amp * 2.0, 1.0)

                if self.style_name == "bars":
                    fft_frame = fft[fi] if fi < len(fft) else np.zeros(80)
                    frame = self.renderer.render_frame(fi, fft_frame, width, height, self.fps)
                elif self.style_name == "envelope":
                    frame = self.renderer.render_frame(fi, env, width, height, self.fps)
                else:
                    frame = self.renderer.render_frame(fi, amp, width, height, self.fps)

                if self.opacity < 1.0:
                    r, g, b, a = frame.split()
                    a = a.point(lambda x: int(x * self.opacity))
                    frame = Image.merge("RGBA", (r, g, b, a))

                # Pipe raw RGBA bytes directly to ffmpeg (no disk I/O)
                ff_proc.stdin.write(frame.tobytes())

            ff_proc.stdin.close()
            ff_proc.wait()
            if ff_proc.returncode != 0:
                raise RuntimeError(f"ffmpeg failed with code {ff_proc.returncode}")

            print("Compositing...")
            import shutil
            shutil.copy2(local_out, output_path)

        print(f"✓ Output: {output_path}")

    @staticmethod
    def _nvenc_available():
        """Check if h264_nvenc encoder is available in this ffmpeg build."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5
            )
            return "h264_nvenc" in result.stdout
        except Exception:
            return False
