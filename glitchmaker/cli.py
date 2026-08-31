"""CLI entry point for glitchmaker."""

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

from .renderer import render_frames
from .compiler import compile_gif

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg"}


def main():
    parser = argparse.ArgumentParser(
        prog="glitchmaker",
        description="Generate glitch art GIFs from static images",
    )
    parser.add_argument("config", nargs="?", help="Path to JSON config file")
    parser.add_argument("--fps", type=int, help="Override fps from config")
    parser.add_argument("--seed", type=int, help="Override seed from config")
    parser.add_argument("--overlap", choices=["stack", "average"], help="Override overlap mode")
    parser.add_argument("--output-dir", help="Override output directory")
    parser.add_argument("--input", help="Override input from config")
    parser.add_argument("--effects", help="Override effects array (JSON array string)")
    parser.add_argument("--no-gif", action="store_true", help="Skip GIF compilation")
    parser.add_argument("--discard-frames", action="store_true", help="Delete frame PNGs after GIF compilation")
    parser.add_argument("--gif-length", type=float, help="Override gif length in seconds")
    parser.add_argument("--benchmark", action="store_true", help="Run with timing, then delete all output")

    args = parser.parse_args()

    # --no-gif and --discard-frames are mutually exclusive
    if args.no_gif and args.discard_frames:
        parser.error("--no-gif and --discard-frames cannot be used together")

    # Config is required
    if not args.config:
        parser.error("config file is required")

    # Load JSON config
    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"In config: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"In $: invalid JSON at line {e.lineno} col {e.colno}: {e.msg}", file=sys.stderr)
            sys.exit(1)

    # CLI overrides — may satisfy required fields
    if args.fps is not None:
        config["fps"] = args.fps
    if args.seed is not None:
        config["seed"] = args.seed
    if args.overlap is not None:
        config["overlap"] = args.overlap
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.gif_length is not None:
        config["gif_length"] = args.gif_length
    if args.input is not None:
        config["input"] = args.input
    if args.effects is not None:
        try:
            parsed = json.loads(args.effects)
        except json.JSONDecodeError as e:
            print(f"In effects: invalid JSON for --effects at line {e.lineno} col {e.colno}: {e.msg}", file=sys.stderr)
            sys.exit(1)
        config["effects"] = parsed

    # Validate config (after defaults + CLI overrides, before I/O) — collect all errors
    from .validate import validate

    errors, warnings = validate(config)

    # File existence/format checks appended to same error set
    if "input" in config and isinstance(config["input"], str) and config["input"].strip():
        input_path = Path(config["input"])
        if not input_path.is_file():
            errors.append({"field": "input", "message": f"input file not found: {config['input']}"})
        elif input_path.suffix.lower() not in SUPPORTED_FORMATS:
            errors.append({"field": "input", "message": f"unsupported format '{input_path.suffix}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"})

    if errors:
        for e in errors:
            print(f"In {e['field']}: {e['message']}", file=sys.stderr)
        for w in warnings:
            print(f"Warning in {w['field']}: {w['message']}", file=sys.stderr)
        sys.exit(1)
    # warnings -> stderr via render_frames (shared path), exit 0 — don't duplicate

    # Render frames — bar is handled inside render_frames (stderr, \r, isatty)
    print("Rendering frames...", file=sys.stderr)
    t_render = time.perf_counter()
    output_dir = render_frames(config)
    t_render = time.perf_counter() - t_render
    frames_dir = str(Path(output_dir) / "frames")
    frame_count = len(list(Path(frames_dir).glob("frame_*.png")))

    gif_path = None
    t_gif = 0

    # Compile GIF (unless --no-gif)
    if not args.no_gif:
        gif_path = str(Path(output_dir) / "glitch.gif")
        print("Compiling GIF...")
        t_gif = time.perf_counter()
        ok = compile_gif(frames_dir, gif_path, config["fps"])
        t_gif = time.perf_counter() - t_gif
        if ok:
            print(f"GIF saved to {gif_path}")
        else:
            print("GIF compilation failed.", file=sys.stderr)
            sys.exit(1)

    # Discard frame PNGs if requested
    if args.discard_frames:
        for f in glob.glob(os.path.join(frames_dir, "frame_*.png")):
            os.remove(f)
        print(f"Discarded frame PNGs from {frames_dir}")

    # Benchmark summary
    if args.benchmark:
        total = t_render + (t_gif if gif_path else 0)
        print(f"\nRendered {frame_count} frames in {t_render:.2f}s")
        if gif_path:
            print(f"Compiled GIF in {t_gif:.2f}s")
        print(f"Total: {total:.2f}s")

    # Summary
    print(f"\nDone: {frame_count} frames generated")
    if gif_path:
        print(f"      {gif_path}")

    # Benchmark cleanup: delete frames + gif
    if args.benchmark:
        for f in glob.glob(os.path.join(frames_dir, "frame_*.png")):
            os.remove(f)
        if gif_path and os.path.isfile(gif_path):
            os.remove(gif_path)


if __name__ == "__main__":
    main()
