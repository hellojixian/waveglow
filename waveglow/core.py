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
from .styles import PlasmaStyle, BarsStyle, EnvelopeStyle


STYLES = {
    "plasma": PlasmaStyle,
    "bars": BarsStyle,
    "envelope": EnvelopeStyle,
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

        # Auto y position: bottom of video
        if y_position is None:
            # detect video height
            import json
            proc = subprocess.run([
                'ffprobe', "-loglevel", "panic",
                str(video_path), '-print_format', 'json', '-show_streams'
            ], capture_output=True)
            info = json.loads(proc.stdout.decode('utf-8'))
            vid_h = next((s['height'] for s in info['streams'] if s.get('codec_type') == 'video'), 1080)
            y_position = vid_h - height

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            frames_dir = tmp / "frames"
            frames_dir.mkdir()

            print(f"Rendering {n_frames} frames...")
            for fi in tqdm(range(n_frames), unit=" frames", ncols=80):
                amp = float(rms[fi]) if fi < len(rms) else 0.0
                amp = min(amp * 2.0, 1.0)

                if self.style_name == "plasma":
                    frame = self.renderer.render_frame(fi, amp, width, height, self.fps)
                elif self.style_name == "bars":
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

                frame.save(frames_dir / f"{fi:06d}.png")

            print("Compositing...")
            # Write to local tmp first (avoid NFS moov truncation)
            local_out = tmp / "output.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "warning",
                "-i", str(video_path.resolve()),
                "-framerate", str(self.fps),
                "-i", str(frames_dir / "%06d.png"),
                "-i", str(audio_path.resolve()),
                "-filter_complex",
                f"[1:v]format=rgba[wv];[0:v][wv]overlay=0:{y_position}:format=auto[outv]",
                "-map", "[outv]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                str(local_out),
            ], check=True)

            import shutil
            shutil.copy2(local_out, output_path)

        print(f"✓ Output: {output_path}")
