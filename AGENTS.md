# AGENTS.md

## Project

Python CLI tool that applies glitch effects to static images and compiles them into animated GIFs.

## Quick Commands

```bash
pip install -r requirements.txt          # Install (Pillow + numpy)
python -m glitchmaker config.json        # Run
python -m glitchmaker config.json --fps 15 --seed 123 --overlap average --no-gif
python -m glitchmaker config.json --benchmark  # Run with timing, auto-cleanup
python showcase.py                       # Generate all 30 showcase GIFs (generally takes under 10 seconds)
python showcase.py --filter noise        # Only entries matching filter term(s)
```

No external dependencies beyond Pillow. GIF compilation uses Pillow's built-in GIF writer.

## Architecture

```
glitchmaker/
  cli.py          # argparse entry point, config validation
  renderer.py     # Frame generation: amplitude calc, effect routing, overlap modes
  effects.py      # 24 individual pixel-manipulation functions (noise, scanLines, chromaticAberration, etc.)
  compiler.py     # Pillow GIF compilation (no external deps)
showcase.py       # Showcase generator: 30 effects (single+overlay+ramp)
```

## Comment & Docstring Convention

- Every function has a plain one-line docstring describing functionality.
- File-wide gotchas belong in the file docstring.
- General functionality note → single `#` line immediately above `def`.
- Line-local nuance → `code  # comment` beside that line. No `ponytail:` by default; use only for deliberate ceiling with upgrade path. When in doubt, preserve.

## Key Gotchas

- **RGB shift offsets are percentages of image dimensions**, not raw pixels. `rgbRedX: 10` = shift 10% of image width. This was changed from raw pixels to make effects consistent across image sizes.
- **`render_frames` clears old frame PNGs** before rendering. The frames directory is NOT wiped, only `frame_*.png` files are removed.
- **Overlap modes:** `stack` = sequential (output of one feeds next), `average` = independent apply + pixel mean (includes original image in average).
- **Ramp:** `false`/omitted/`"constant"` = constant amplitude, `"ascend"` = linear 0 → amplitude, `"descend"` = linear amplitude → 0, `"peak"` = symmetric 0 → amplitude → 0.
- **Seed is set once** at start of `render_frames`, not per-frame. Each frame gets different random values from the progressing RNG sequence.
- **Effects start on frame 1** — no clean/unmodified first frame.
- **Input formats:** PNG, JPG, JPEG only (validated in cli.py).

## Showcase

`showcase.py` generates 30 showcase GIFs: 24 single-effect + 2 overlay + 4 ramp. All are 1.5s at 12fps (18 frames), verified to contain 18 frames.
