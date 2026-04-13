"""
WaveGlow CLI
"""

import argparse
from pathlib import Path
from .core import WaveGlow


def parse_color(s):
    try:
        r, g, b = [float(x) for x in s.split(",")]
        return (r, g, b)
    except Exception:
        raise argparse.ArgumentTypeError("Color must be 'r,g,b' floats in [0,1], e.g. 0.3,0.7,1.0")


def add_common_args(parser):
    parser.add_argument("--style", choices=["plasma", "bars", "envelope", "glow-edge"], default="plasma")
    parser.add_argument("--color", type=parse_color, default=None,
                        help="Primary color r,g,b in [0,1] (default: blue)")
    parser.add_argument("--color2", type=parse_color, default=None,
                        help="Secondary color r,g,b in [0,1] (default: white)")
    parser.add_argument("--glow", type=float, default=5.0, help="Glow intensity 0-10")
    parser.add_argument("--lines", type=int, default=8, help="Number of plasma lines")
    parser.add_argument("--bars", type=int, default=80, help="Number of bars")
    parser.add_argument("--speed", type=float, default=4.0, help="Animation speed")
    parser.add_argument("--opacity", type=float, default=1.0, help="Overall opacity 0-1")
    parser.add_argument("--fps", type=int, default=30, help="Framerate")
    parser.add_argument("--width", type=int, default=1920, help="Waveform width in pixels")
    parser.add_argument("--height", type=int, default=200, help="Waveform height in pixels")


def cmd_render(args):
    wg = WaveGlow(
        style=args.style,
        color=args.color,
        color2=args.color2,
        glow=args.glow,
        lines=args.lines,
        bars=args.bars,
        speed=args.speed,
        opacity=args.opacity,
        fps=args.fps,
    )
    bg = None
    if hasattr(args, "bg") and args.bg and args.bg != "transparent":
        bg = parse_color(args.bg)

    wg.render(
        audio_path=args.audio,
        output_path=args.output,
        width=args.width,
        height=args.height,
        bg=bg,
    )


def cmd_overlay(args):
    wg = WaveGlow(
        style=args.style,
        color=args.color,
        color2=args.color2,
        glow=args.glow,
        lines=args.lines,
        bars=args.bars,
        speed=args.speed,
        opacity=args.opacity,
        fps=args.fps,
    )
    wg.overlay(
        audio_path=args.audio,
        video_path=args.video,
        output_path=args.output,
        y_position=args.y,
        width=args.width,
        height=args.height,
    )


def main():
    parser = argparse.ArgumentParser(
        prog="waveglow",
        description="WaveGlow — Beautiful audio waveform visualizations with glow effects",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # render subcommand
    render_p = subparsers.add_parser("render", help="Generate standalone waveform video")
    render_p.add_argument("audio", type=Path, help="Input audio file")
    render_p.add_argument("--output", "-o", type=Path, default=Path("out.mp4"))
    render_p.add_argument("--bg", default="transparent",
                          help="Background: 'transparent' or r,g,b in [0,1]")
    add_common_args(render_p)
    render_p.set_defaults(func=cmd_render)

    # overlay subcommand
    overlay_p = subparsers.add_parser("overlay", help="Overlay waveform onto a video")
    overlay_p.add_argument("audio", type=Path, help="Input audio file")
    overlay_p.add_argument("--video", "-v", type=Path, required=True, help="Input video file")
    overlay_p.add_argument("--output", "-o", type=Path, default=Path("out.mp4"))
    overlay_p.add_argument("--y", type=int, default=None,
                           help="Y position from top (default: auto = bottom)")
    add_common_args(overlay_p)
    overlay_p.set_defaults(func=cmd_overlay)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
