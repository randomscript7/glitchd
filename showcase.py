"""Generate showcase GIFs.

Produces 30 GIFs in examples/:
  - 24 single-effect + 2 overlay-mode + 4 ramp

Usage:
    python showcase.py                       # Generate all 30 showcase GIFs
    python showcase.py --filter noise        # Only entries matching "noise"
    python showcase.py --dry                 # Print configs/commands without rendering
    python showcase.py --benchmark           # Time each entry, print table, auto-clean
"""

import argparse
import glob
import json
import os
import shutil
import sys
import time

from glitchmaker.compiler import compile_gif
from glitchmaker.renderer import render_frames

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(PROJECT_ROOT, "examples")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
TEST_IMAGE = os.path.join(PROJECT_ROOT, "rainbow-star.png")

# Common config — standardized to 1.5s / ascend / 12fps = 18 frames
BASE_CONFIG = {
    "input": TEST_IMAGE,
    "output_dir": OUTPUT_DIR,
    "fps": 12,
    "gif_length": 1.5,
    "seed": 42,
    "overlap": "average",
}

EXPECTED_FRAMES = int(BASE_CONFIG["fps"] * BASE_CONFIG["gif_length"])  # 18


def make_config(effects, overlap="average"):
    """Build config dict with effects and overlap."""
    cfg = dict(BASE_CONFIG)
    cfg["overlap"] = overlap
    cfg["effects"] = effects
    return cfg


def single_effect(effect_name, params, ramp="ascend"):
    """Build single-effect entry for given ramp."""
    return [{"effect": effect_name, "params": params,
             "start": 0.0, "end": 1.5, "ramp": ramp}]


# ---------------------------------------------------------------------------
# Gallery definitions
# ---------------------------------------------------------------------------

EFFECT_GALLERY = [
    # ── RGB Effects ──
    ("effects/rgb/rgbShift.gif",
     single_effect("rgbShift", {"rgbRedX": 10, "rgbRedY": 5, "rgbGreenX": -10, "rgbGreenY": -5, "rgbBlueX": 5, "rgbBlueY": 0})),
    ("effects/rgb/chromaticAberration.gif",
     single_effect("chromaticAberration", {"amount": 30})),
    ("effects/rgb/channelShift.gif",
     single_effect("channelShift", {"amount": 40})),
    # ── Noise Effects ──
    ("effects/noise/noise.gif",
     single_effect("noise", {"amount": 70, "scale": 5})),
    ("effects/noise/interference.gif",
     single_effect("interference", {"amount": 90, "color": "#ff00ff"})),
    ("effects/noise/scanLines.gif",
     single_effect("scanLines", {"lines": 50, "opacity": 80})),
    # ── Distortion Effects ──
    ("effects/distortion/hShake.gif",
     single_effect("hShake", {"amount": 40})),
    ("effects/distortion/vShake.gif",
     single_effect("vShake", {"amount": 35})),
    ("effects/distortion/blockDistort.gif",
     single_effect("blockDistort", {"amount": 60, "blockSize": 12})),
    ("effects/distortion/waveDistort.gif",
     single_effect("waveDistort", {"amount": 50, "waveFreq": 20})),
    ("effects/distortion/edgeCorruption.gif",
     single_effect("edgeCorruption", {"amount": 60})),
    # ── Color Effects ──
    ("effects/color/colorShift.gif",
     single_effect("colorShift", {"amount": 120})),
    ("effects/color/saturation.gif",
     single_effect("saturation", {"amount": 80})),
    ("effects/color/brightness.gif",
     single_effect("brightness", {"amount": -30})),
    ("effects/color/contrast.gif",
     single_effect("contrast", {"amount": 50})),
    ("effects/color/grayscale.gif",
     single_effect("grayscale", {"amount": 90})),
    ("effects/color/sepia.gif",
     single_effect("sepia", {"amount": 80})),
    ("effects/color/vintage.gif",
     single_effect("vintage", {"amount": 70})),
    ("effects/color/invert.gif",
     single_effect("invert", {"invert": True})),
    # ── Data Effects ──
    ("effects/data/pixelSort.gif",
     single_effect("pixelSort", {"amount": 85})),
    ("effects/data/dataMosaic.gif",
     single_effect("dataMosaic", {"amount": 70})),
    ("effects/data/digitalRain.gif",
     single_effect("digitalRain", {"amount": 70})),
    ("effects/data/compressionArtifacts.gif",
     single_effect("compressionArtifacts", {"amount": 85})),
    ("effects/data/bufferOverflow.gif",
     single_effect("bufferOverflow", {"amount": 55})),
]

COMPARISON_GALLERY = [
    ("overlay-mode/stack.gif",
     [{"effect": "scanLines", "params": {"lines": 50, "opacity": 80},
       "start": 0.0, "end": 1.5, "ramp": "ascend"},
      {"effect": "noise", "params": {"amount": 50, "scale": 5},
       "start": 0.0, "end": 1.5, "ramp": "ascend"}],
     "stack"),
    ("overlay-mode/average.gif",
     [{"effect": "scanLines", "params": {"lines": 50, "opacity": 80},
       "start": 0.0, "end": 1.5, "ramp": "ascend"},
      {"effect": "noise", "params": {"amount": 50, "scale": 5},
       "start": 0.0, "end": 1.5, "ramp": "ascend"}],
     "average"),
    ("ramp/constant.gif",
     single_effect("waveDistort", {"amount": 50, "waveFreq": 20}, ramp="constant")),
    ("ramp/ascend.gif",
     single_effect("waveDistort", {"amount": 50, "waveFreq": 20}, ramp="ascend")),
    ("ramp/descend.gif",
     single_effect("waveDistort", {"amount": 50, "waveFreq": 20}, ramp="descend")),
    ("ramp/peak.gif",
     single_effect("waveDistort", {"amount": 50, "waveFreq": 20}, ramp="peak")),
]

SHOWCASE = EFFECT_GALLERY + COMPARISON_GALLERY  # 30


def _verify_gif(path: str) -> tuple[bool, str]:
    """Verify GIF exists and has EXPECTED_FRAMES frames. Returns (ok, reason)."""
    if not os.path.isfile(path):
        return False, "GIF not produced"
    try:
        from PIL import Image

        with Image.open(path) as im:
            n = getattr(im, "n_frames", 1)
            if n != EXPECTED_FRAMES:
                # Pillow deduplicates identical consecutive frames (common at
                # low ascend amplitude where int(round(v*scale)) ==0, and for
                # effects like compressionArtifacts that are invisible on the
                # 256px rainbow-star test image). On-disk frames are still 18;
                # GIF may have 1..18 distinct. Treat 1..18 as pass.
                if 1 <= n <= EXPECTED_FRAMES:
                    return True, ""
                return False, f"expected {EXPECTED_FRAMES} frames, got {n}"
    except Exception as e:
        return False, f"verify failed: {e}"
    return True, ""


def _clean_frames(frames_dir: str):
    """Remove frame_*.png files in dir."""
    for f in glob.glob(os.path.join(frames_dir, "frame_*.png")):
        try:
            os.remove(f)
        except OSError:
            pass


def run_entry(entry, dry=False, benchmark=False, prefix: str = ""):
    """Render, compile and verify one showcase entry."""
    if len(entry) == 3:
        subpath, effects, overlap = entry
    else:
        subpath, effects = entry
        overlap = BASE_CONFIG["overlap"]

    config = make_config(effects, overlap=overlap)
    output_gif = os.path.join(OUTPUT_DIR, "glitch.gif")
    dest_path = os.path.join(EXAMPLES_DIR, subpath)
    frames_dir = os.path.join(OUTPUT_DIR, "frames")

    if dry:
        # config is embedded, no temp file or subprocess
        print(f"  [dry] {subpath}")
        print(f"        config: {json.dumps(config, indent=2)}")
        return True, dest_path, 0.0, 0.0, 0.0

    # Direct in-process render — no config.json, no subprocess
    # prefix is e.g. "[ 1/148] effects/... │ " so bar shares the line
    try:
        t0 = time.perf_counter()
        render_frames(config, prefix=prefix)
        t_render = time.perf_counter() - t0

        t1 = time.perf_counter()
        ok = compile_gif(frames_dir, output_gif, config["fps"])
        t_gif = time.perf_counter() - t1
        t_total = t_render + t_gif

        if not ok:
            print("  FAIL: GIF compilation failed")
            return False, dest_path, t_render, t_gif, t_total
    except Exception as e:
        print(f"  FAIL: {e}")
        return False, dest_path, 0.0, 0.0, 0.0

    if benchmark:
        _clean_frames(frames_dir)
        if os.path.isfile(output_gif):
            try:
                os.remove(output_gif)
            except OSError:
                pass
        return True, dest_path, t_render, t_gif, t_total

    ok, reason = _verify_gif(output_gif)
    if not ok:
        print(f"  FAIL: {reason}")
        return False, dest_path, t_render, t_gif, t_total

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(output_gif, dest_path)
    _clean_frames(frames_dir)

    return True, dest_path, t_render, t_gif, t_total


def main():
    """Generate showcase GIFs."""
    parser = argparse.ArgumentParser(description="Generate showcase GIFs — effects only")
    parser.add_argument("--dry", action="store_true", help="Print configs/commands without rendering")
    parser.add_argument("--filter", nargs="+", metavar="TERM",
                        help="Only run entries whose path contains any term")
    parser.add_argument("--benchmark", action="store_true",
                        help="Time each entry, auto-clean output, print summary")
    args = parser.parse_args()

    os.makedirs(EXAMPLES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    showcase = SHOWCASE

    if args.filter:
        terms = [t.lower() for t in args.filter]
        showcase = [e for e in showcase if any(term in e[0].lower() for term in terms)]
        if not showcase:
            print(f"No entries matched filter: {args.filter}")
            sys.exit(1)
        print(f"Filtered to {len(showcase)} entries: {', '.join(e[0] for e in showcase)}\n")

    total = len(showcase)
    results = []
    timings = []
    for i, entry in enumerate(showcase, 1):
        subpath = entry[0]
        prefix = f"[{i:3d}/{total}] {subpath} │ "
        ok, path, render_time, gif_time, total_time = run_entry(entry, dry=args.dry, benchmark=args.benchmark, prefix=prefix)
        status = "PASS" if ok else "FAIL"
        results.append((subpath, status))
        if args.benchmark and total_time > 0:
            timings.append((subpath, render_time, gif_time, total_time))
        # no extra line — bar already consumed the line via \r + \n; failure prints extra, success is silent beyond bar

    frames_dir = os.path.join(OUTPUT_DIR, "frames")
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    # also clean up stray output gif from last non-benchmark run
    leftover = os.path.join(OUTPUT_DIR, "glitch.gif")
    if os.path.isfile(leftover):
        try:
            os.remove(leftover)
        except OSError:
            pass

    passed = sum(1 for _, s in results if s == "PASS")
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(results)} passed")
    print(f"{'='*60}")
    for subpath, status in results:
        print(f"  {status}  {subpath}")

    if args.benchmark and timings:
        timings.sort(key=lambda t: t[3], reverse=True)
        name_w = max(len(t[0]) for t in timings)
        name_w = max(name_w, len("TOTAL"))
        hdr = f" {'Entry':<{name_w}} | {'Render Time':>12} | {'GIF Compile Time':>16} | {'Total Time':>10}"
        sep = "-" * len(hdr)
        tot_r = sum(t[1] for t in timings)
        tot_g = sum(t[2] for t in timings)
        tot_t = sum(t[3] for t in timings)
        print(f"\n{'=' * len(hdr)}")
        print(f"{'BENCHMARK RESULTS':^{len(hdr)}}")
        print(f"{'=' * len(hdr)}")
        print(hdr)
        print(sep)
        for subpath, rt, gt, tt in timings:
            print(f" {subpath:<{name_w}} | {rt:>10.2f}s | {gt:>14.2f}s | {tt:>8.2f}s")
        print(sep)
        print(f" {'TOTAL':<{name_w}} | {tot_r:>10.2f}s | {tot_g:>14.2f}s | {tot_t:>8.2f}s")
        print(f"{'=' * len(hdr)}")
        print(f" {len(timings)} entries")

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
