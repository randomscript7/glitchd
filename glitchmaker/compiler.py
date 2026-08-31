"""Compile frame PNGs into a GIF using Pillow."""

import glob
import os

from PIL import Image


def compile_gif(frames_dir: str, output_path: str, fps: int) -> bool:
    """Compile PNG frames into a GIF.

    Args:
        frames_dir: Directory containing PNGs named frame_*.png.
        output_path: Output path for the resulting .gif file.
        fps: Frames per second for the output GIF.

    Returns:
        True on success, False on failure.
    """
    # Pillow uses per-frame palettes (no global palette optimization
    # like ffmpeg's palettegen). Acceptable for glitch art aesthetic.
    frame_paths = sorted(glob.glob(os.path.join(frames_dir, "frame_*.png")))
    if not frame_paths:
        return False

    frames = [Image.open(p).convert("RGB") for p in frame_paths]
    duration = int(1000 / fps)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        optimize=False,
    )
    return True
