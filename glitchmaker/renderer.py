"""Generates glitch frames from an input image based on a JSON config."""

import glob
import os
import random
import sys

import numpy as np
from PIL import Image

from .effects import EFFECTS


def render_frames(config: dict, verbose: bool | None = None, prefix: str = "") -> str:
    """Main entry point. Returns the output_dir path.

    verbose: None = auto (isatty), True/False = force. When True, a single-line
             overwriting bar is written to stderr (with prefix). When False or
             not tty, a final status line is printed instead.
    prefix:  string prepended to the bar (e.g. "[ 1/148] effects/... │ ")
    """
    # validate all configs (file + programmatic) — errors raise, warnings -> stderr plain, exit 0
    from .validate import validate

    errors, warnings = validate(config)
    if errors:
        lines = [f"In {e['field']}: {e['message']}" for e in errors] + [f"Warning in {w['field']}: {w['message']}" for w in warnings]
        raise ValueError("\n".join(lines))
    if warnings:
        for w in warnings:
            print(f"Warning in {w['field']}: {w['message']}", file=sys.stderr)

    total_frames = int(config["gif_length"] * config["fps"])
    output_dir = os.path.join(config["output_dir"], "frames")

    # Clear old frames to prevent stale files from prior runs
    for old_frame in glob.glob(os.path.join(output_dir, "frame_*.png")):
        os.remove(old_frame)
    os.makedirs(output_dir, exist_ok=True)

    # Seed once at the start. Each frame naturally gets different random
    # values as the RNG sequence progresses.
    if config.get("seed") is not None:
        random.seed(config["seed"])
        np.random.seed(config["seed"])

    img = Image.open(config["input"]).convert("RGB")

    use_bar = sys.stderr.isatty() if verbose is None else bool(verbose)
    last_len = 0

    for i in range(total_frames):
        frame = _generate_frame(
            img, config["effects"], i,
            config["fps"], config.get("overlap", "stack"),
        )
        frame.save(os.path.join(output_dir, f"frame_{i + 1:04d}.png"))
        if use_bar:
            msg = f"{prefix}Frame {i + 1}/{total_frames}"
            pad = " " * max(last_len - len(msg), 0)  # compat: no \033[K
            sys.stderr.write(f"\r{msg}{pad}")
            sys.stderr.flush()
            last_len = len(msg)

    if use_bar:
        sys.stderr.write("\n")
        sys.stderr.flush()
    else:
        # fallback final line when not tty (e.g. CI, > log.txt)
        print(f"{prefix}Generated {total_frames} frames in {output_dir}", file=sys.stderr)

    return config["output_dir"]


def _calculate_amplitude(effect_entry: dict, frame_idx: int, fps: int) -> float:
    """Returns the effective amplitude for a given frame, or 0 if inactive."""
    # amplitude is internal ramping scale only, not a config field
    amplitude = 100
    start_frame = int(effect_entry.get("start", 0) * fps)
    end_frame = int(effect_entry.get("end", 0) * fps)
    effect_frames = end_frame - start_frame

    if frame_idx < start_frame or frame_idx >= end_frame:
        return 0.0

    # invert is binary — ramp would make ascend/peak hit amp==0 on first frame -> skip
    # so invert ignores ramp and is always constant when active; one guard in shared path fixes all callers
    if effect_entry.get("effect") == "invert" or effect_entry.get("params", {}).get("invert"):
        return amplitude

    ramp = effect_entry.get("ramp")
    if ramp and ramp != "constant" and effect_frames > 0:
        progress = (frame_idx - start_frame) / effect_frames
        if ramp == "ascend":
            return amplitude * progress
        elif ramp == "descend":
            return amplitude * (1 - progress)
        elif ramp == "peak":
            return amplitude * (1 - abs(2 * progress - 1))

    return amplitude


def _resolve_effect_entries(effect_entry: dict, amplitude: float) -> list:
    """Resolve an effect entry into a list of (effect_fn, params) tuples."""
    if "effect" in effect_entry:
        effect_fn = EFFECTS.get(effect_entry["effect"])
        if effect_fn:
            # scale numeric params by amplitude so ramp produces
            # gradual frames (otherwise ascend would be binary off/on → 2 GIF frames)
            # keep bool intact, round ints to avoid float slice indices
            # ponytail: structural sizes (blockSize/waveFreq/lines/scale) are not
            # ramped — scaling them to 0 triggers range(...,0) ValueError on early
            # ascend frames; only intensity params (amount/rgb*/opacity) scale.
            scale = amplitude / 100.0
            raw = effect_entry.get("params", {})
            scaled: dict = {}
            _STRUCTURAL = {"blockSize", "waveFreq", "lines", "scale"}
            for k, v in raw.items():
                if isinstance(v, bool):
                    scaled[k] = v
                elif k in _STRUCTURAL:
                    scaled[k] = v
                elif isinstance(v, int):
                    # preserve int type for params like amount/rgb*/opacity
                    scaled[k] = int(round(v * scale))
                elif isinstance(v, float):
                    scaled[k] = v * scale
                else:
                    scaled[k] = v
            return [(effect_fn, scaled)]

    return []


def _apply_effects_stack(img: Image.Image, active_effects: list) -> Image.Image:
    """Apply effects in order. Each effect's output becomes the next input."""
    result = img.copy()
    for effect_fn, params in active_effects:
        result = effect_fn(result, params)
    return result


def _apply_effects_average(img: Image.Image, active_effects: list) -> Image.Image:
    """Apply each effect independently to the original, then average all pixel values."""
    if not active_effects:
        return img.copy()

    # invert+original average is degenerate ((x + (255-x))/2 == 127 -> solid grey)
    # so exclude original when any active effect is invert; one guard in shared path fixes all callers
    include_original = not any(p.get("invert") for _, p in active_effects)
    results = [img.copy()] if include_original else []
    for effect_fn, params in active_effects:
        results.append(effect_fn(img.copy(), params))

    arrs = [np.array(r, dtype=np.uint16) for r in results]
    stacked = np.stack(arrs, axis=0)  # (n, h, w, 3)
    avg = (stacked.sum(axis=0) // len(arrs)).astype(np.uint8)
    return Image.fromarray(avg)


def _generate_frame(
    source_img: Image.Image,
    effects_config: list,
    frame_idx: int,
    fps: int,
    overlap: str = "stack",
) -> Image.Image:
    """Generate a single frame with active effects applied."""
    active_effects = []
    for entry in effects_config:
        amp = _calculate_amplitude(entry, frame_idx, fps)
        if amp <= 0:
            continue
        active_effects.extend(_resolve_effect_entries(entry, amp))

    if not active_effects:
        return source_img.copy()

    if overlap == "average":
        return _apply_effects_average(source_img, active_effects)
    return _apply_effects_stack(source_img, active_effects)
