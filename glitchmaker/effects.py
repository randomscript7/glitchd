"""Image glitch effects module.

Use numpy for accelerated pixel manipulation. Every effect
function takes a PIL Image and a params dict, returns a new modified PIL Image.

Random generation uses Python's ``random`` module (not numpy's RNG) to
preserve seed reproducibility with the renderer's ``random.seed()`` call.
"""

import random
import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_arr(img):
    """PIL Image -> numpy array (h, w, 3) uint8."""
    return np.array(img, dtype=np.uint8)


def _to_img(arr):
    """numpy array -> PIL Image, clamped to [0, 255]."""
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _bulk_random(h, w):
    """Generate (h, w) random floats [0, 1). Uses numpy RNG (seeded in renderer)."""
    return np.random.rand(h, w)


# ---------------------------------------------------------------------------
# Effect: RGB Shift
# ---------------------------------------------------------------------------

def rgb_shift(img, params):
    """Channel offset for R, G, B independently.

    Offset values are treated as percentages of image dimensions so the
    effect scales consistently across different image sizes.
    """
    red_x = params.get("rgbRedX", 0)
    red_y = params.get("rgbRedY", 0)
    green_x = params.get("rgbGreenX", 0)
    green_y = params.get("rgbGreenY", 0)
    blue_x = params.get("rgbBlueX", 0)
    blue_y = params.get("rgbBlueY", 0)

    if not any([red_x, red_y, green_x, green_y, blue_x, blue_y]):
        return img.copy()

    arr = _to_arr(img)
    h, w = arr.shape[:2]
    sx, sy = w / 100.0, h / 100.0
    out = np.zeros_like(arr)

    def _offset_channel(ch, ox, oy):
        Y = np.arange(h)[:, None]
        X = np.arange(w)
        src_y = np.clip(Y + oy, 0, h - 1)
        src_x = np.clip(X + ox, 0, w - 1)
        return arr[src_y, src_x, ch]

    out[:,:,0] = _offset_channel(0, int(red_x * sx), int(red_y * sy))
    out[:,:,1] = _offset_channel(1, int(green_x * sx), int(green_y * sy))
    out[:,:,2] = _offset_channel(2, int(blue_x * sx), int(blue_y * sy))
    return _to_img(out)


# ---------------------------------------------------------------------------
# Effect: Noise
# ---------------------------------------------------------------------------

def apply_noise(img, params):
    """Random pixel noise."""
    amount = params.get("amount", 0)
    scale = params.get("scale", 5)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    h, w = arr.shape[:2]
    X = np.arange(w, dtype=np.float32)[None, :]
    Y = np.arange(h, dtype=np.float32)[:, None]
    noise_mul = 1 + np.sin(X * scale * 0.01) * np.cos(Y * scale * 0.01)
    delta = (_bulk_random(h, w) - 0.5) * amount * 2.55 * noise_mul
    arr += delta[:,:,np.newaxis]
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Scan Lines
# ---------------------------------------------------------------------------

def apply_scan_lines(img, params):
    """Horizontal darkening lines."""
    lines = params.get("lines", 0)
    opacity = params.get("opacity", 0)

    if lines <= 0 or opacity <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    h = arr.shape[0]
    line_h = max(1, 100 // lines)
    factor = 1 - opacity * 0.7 / 100

    # Build mask: darken every other band
    mask = np.ones(h, dtype=np.float32)
    mask[line_h::line_h * 2] = factor
    arr *= mask[:, np.newaxis, np.newaxis]
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Interference
# ---------------------------------------------------------------------------

def apply_interference(img, params):
    """Colored horizontal bars."""
    amount = params.get("amount", 0)
    color_hex = params.get("color", "#ff00ff")

    if amount <= 0:
        return img.copy()

    # Parse hex color
    h_str = color_hex.lstrip("#")
    cr, cg, cb = int(h_str[0:2], 16), int(h_str[2:4], 16), int(h_str[4:6], 16)

    arr = _to_arr(img).astype(np.float32)
    h, w = arr.shape[:2]
    num_bars = int(amount // 10)

    for _ in range(num_bars):
        bar_x = random.randint(0, w - 1)
        bar_w = random.randint(5, 25)
        bar_h = random.randint(50, 150)
        bar_y = random.randint(0, h - 1)

        # Clip bar bounds to image
        y0 = max(0, bar_y)
        y1 = min(h, bar_y + bar_h)
        x0 = max(0, bar_x)
        x1 = min(w, bar_x + bar_w)
        if y1 <= y0 or x1 <= x0:
            continue

        # Sin modulation within bar
        dy = np.arange(y1 - y0)[:, np.newaxis]
        dx = np.arange(x1 - x0)[np.newaxis, :]
        val = np.sin((dx + dy) * 0.5) * 50

        if cr > 128:
            arr[y0:y1, x0:x1, 0] += val * cr / 255
        if cg > 128:
            arr[y0:y1, x0:x1, 1] += val * cg / 255
        if cb > 128:
            arr[y0:y1, x0:x1, 2] += val * cb / 255

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: H Shake
# ---------------------------------------------------------------------------

def apply_h_shake(img, params):
    """Horizontal shake (random horizontal offset for the whole image)."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    ox = int((random.random() - 0.5) * amount)
    arr = np.roll(_to_arr(img), ox, axis=1)
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: V Shake
# ---------------------------------------------------------------------------

def apply_v_shake(img, params):
    """Vertical shake (random vertical offset for the whole image)."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    oy = int((random.random() - 0.5) * amount)
    arr = np.roll(_to_arr(img), oy, axis=0)
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Block Distort
# ---------------------------------------------------------------------------

def apply_block_distort(img, params):
    """Random block offsets."""
    amount = params.get("amount", 0)
    block_size = params.get("blockSize", 8)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).copy()
    h, w = arr.shape[:2]

    for by in range(0, h, block_size):
        for bx in range(0, w, block_size):
            if random.random() < amount / 100.0:
                ox = int((random.random() - 0.5) * amount * 0.5)
                oy = int((random.random() - 0.5) * amount * 0.5)
                y0, y1 = by, min(by + block_size, h)
                x0, x1 = bx, min(bx + block_size, w)
                sy0 = np.clip(y0 + oy, 0, h - 1)
                sx0 = np.clip(x0 + ox, 0, w - 1)
                sh = min(y1 - y0, h - sy0)
                sw = min(x1 - x0, w - sx0)
                if sh > 0 and sw > 0:
                    arr[y0:y0+sh, x0:x0+sw] = arr[sy0:sy0+sh, sx0:sx0+sw].copy()

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Wave Distort
# ---------------------------------------------------------------------------

def apply_wave_distort(img, params):
    """Sinusoidal Y warp."""
    amount = params.get("amount", 0)
    freq = params.get("waveFreq", 10)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img)
    h, w = arr.shape[:2]
    X = np.arange(w)
    offsets = (np.sin(X * freq * 0.01) * amount * 0.5).astype(np.int32)

    Y = np.arange(h)[:, None]
    src_y = np.clip(Y + offsets, 0, h - 1)
    out = arr[src_y, X]
    return _to_img(out)


# ---------------------------------------------------------------------------
# Effect: Pixel Sort
# ---------------------------------------------------------------------------

def apply_pixel_sort(img, params):
    """Sort adjacent pixels by brightness."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).copy()
    h, w = arr.shape[:2]
    threshold = amount / 100.0 * 255

    b = 0.299 * arr[:, :, 0].astype(np.float32) + 0.587 * arr[:, :, 1].astype(np.float32) + 0.114 * arr[:, :, 2].astype(np.float32)
    mask = np.abs(np.diff(b, axis=1)) < threshold
    for i in range(w - 1):
        rows = np.where(mask[:, i])[0]
        if rows.size:
            tmp = arr[rows, i].copy()
            arr[rows, i] = arr[rows, i + 1]
            arr[rows, i + 1] = tmp

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Data Mosaic
# ---------------------------------------------------------------------------

def apply_data_mosaic(img, params):
    """Block-average pixels into mosaic blocks."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).copy()
    h, w = arr.shape[:2]
    mosaic_size = max(2, int(20 * amount / 100))

    for by in range(0, h, mosaic_size):
        for bx in range(0, w, mosaic_size):
            y1 = min(by + mosaic_size, h)
            x1 = min(bx + mosaic_size, w)
            cx = min(bx + mosaic_size // 2, w - 1)
            cy = min(by + mosaic_size // 2, h - 1)
            arr[by:y1, bx:x1] = arr[cy, cx]

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Contrast
# ---------------------------------------------------------------------------

def apply_contrast(img, params):
    """Adjust contrast."""
    amount = params.get("amount", 0)

    if amount == 0:
        return img.copy()

    cf = (259 * (amount + 255)) / (255 * (259 - amount))
    arr = _to_arr(img).astype(np.float32)
    arr = cf * (arr - 128) + 128
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Brightness
# ---------------------------------------------------------------------------

def apply_brightness(img, params):
    """Adjust brightness."""
    amount = params.get("amount", 0)

    if amount == 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    arr += amount / 100.0 * 255
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Saturation
# ---------------------------------------------------------------------------

def apply_saturation(img, params):
    """Adjust saturation."""
    amount = params.get("amount", 0)

    if amount == 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    sf = 1 + amount / 100.0
    gray = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
    arr[:,:,0] = gray + sf * (arr[:,:,0] - gray)
    arr[:,:,1] = gray + sf * (arr[:,:,1] - gray)
    arr[:,:,2] = gray + sf * (arr[:,:,2] - gray)
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Grayscale
# ---------------------------------------------------------------------------

def apply_grayscale(img, params):
    """Convert toward grayscale."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    f = amount / 100.0
    gray = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
    arr[:,:,0] += (gray - arr[:,:,0]) * f
    arr[:,:,1] += (gray - arr[:,:,1]) * f
    arr[:,:,2] += (gray - arr[:,:,2]) * f
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Sepia
# ---------------------------------------------------------------------------

def apply_sepia(img, params):
    """Apply sepia tone."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    f = amount / 100.0
    sr = np.clip(0.393 * arr[:,:,0] + 0.769 * arr[:,:,1] + 0.189 * arr[:,:,2], 0, 255)
    sg = np.clip(0.349 * arr[:,:,0] + 0.686 * arr[:,:,1] + 0.168 * arr[:,:,2], 0, 255)
    sb = np.clip(0.272 * arr[:,:,0] + 0.534 * arr[:,:,1] + 0.131 * arr[:,:,2], 0, 255)
    arr[:,:,0] += (sr - arr[:,:,0]) * f
    arr[:,:,1] += (sg - arr[:,:,1]) * f
    arr[:,:,2] += (sb - arr[:,:,2]) * f
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Vintage
# ---------------------------------------------------------------------------

def apply_vintage(img, params):
    """Apply vintage color wash."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    f = amount / 100.0
    vr = np.clip(arr[:,:,0] * 1.1 + 15, 0, 255)
    vg = np.clip(arr[:,:,1] * 1.0 + 5, 0, 255)
    vb = np.clip(arr[:,:,2] * 0.8 + 10, 0, 255)
    arr[:,:,0] += (vr - arr[:,:,0]) * f
    arr[:,:,1] += (vg - arr[:,:,1]) * f
    arr[:,:,2] += (vb - arr[:,:,2]) * f
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Invert
# ---------------------------------------------------------------------------

def apply_invert(img, params):
    """Invert colors."""
    if not params.get("invert", False):
        return img.copy()
    return _to_img(255 - _to_arr(img))


# ---------------------------------------------------------------------------
# Effect: Color Shift (Hue Rotation)
# ---------------------------------------------------------------------------

def _rgb_to_hsl(arr):
    """Convert (h, w, 3) uint8 RGB array to HSL arrays each in [0, 1]."""
    r = arr[:,:,0].astype(np.float32) / 255.0
    g = arr[:,:,1].astype(np.float32) / 255.0
    b = arr[:,:,2].astype(np.float32) / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    l = (mx + mn) / 2.0

    h = np.zeros_like(l)
    s = np.zeros_like(l)
    d = mx - mn
    nonzero = d > 0

    # Saturation
    s[nonzero] = np.where(
        l[nonzero] > 0.5,
        d[nonzero] / (2.0 - mx[nonzero] - mn[nonzero]),
        d[nonzero] / (mx[nonzero] + mn[nonzero])
    )

    # Hue
    is_r = nonzero & (mx == r)
    is_g = nonzero & (mx == g)
    is_b = nonzero & (mx == b)
    h[is_r] = ((g[is_r] - b[is_r]) / d[is_r] + (np.where(g[is_r] < b[is_r], 6, 0))) / 6.0
    h[is_g] = ((b[is_g] - r[is_g]) / d[is_g] + 2) / 6.0
    h[is_b] = ((r[is_b] - g[is_b]) / d[is_b] + 4) / 6.0

    return h, s, l


def _hue_to_rgb(p, q, t):
    """Hue-to-RGB for HSL->RGB conversion."""
    t = t % 1.0
    out = np.empty_like(t)
    mask1 = t < 1/6
    mask2 = (t >= 1/6) & (t < 1/2)
    mask3 = (t >= 1/2) & (t < 2/3)
    mask4 = t >= 2/3
    out[mask1] = p[mask1] + (q[mask1] - p[mask1]) * 6 * t[mask1]
    out[mask2] = q[mask2]
    out[mask3] = p[mask3] + (q[mask3] - p[mask3]) * (2/3 - t[mask3]) * 6
    out[mask4] = p[mask4]
    return out


def _hsl_to_rgb(h, s, l):
    """Convert HSL arrays (each in [0, 1]) to (h, w, 3) uint8 RGB."""
    rgb = np.zeros((*h.shape, 3), dtype=np.float32)
    achromatic = s == 0
    v = (l * 255).astype(np.uint8)
    rgb[achromatic, 0] = v[achromatic]
    rgb[achromatic, 1] = v[achromatic]
    rgb[achromatic, 2] = v[achromatic]

    q = np.where(l < 0.5, l * (1 + s), l + s - l * s)
    p = 2 * l - q
    not_achromatic = ~achromatic
    rgb[not_achromatic, 0] = _hue_to_rgb(p, q, h + 1/3)[not_achromatic] * 255
    rgb[not_achromatic, 1] = _hue_to_rgb(p, q, h)[not_achromatic] * 255
    rgb[not_achromatic, 2] = _hue_to_rgb(p, q, h - 1/3)[not_achromatic] * 255
    return np.clip(rgb, 0, 255).astype(np.uint8)


def apply_color_shift(img, params):
    """Hue rotation."""
    amount = params.get("amount", 0)

    if amount == 0:
        return img.copy()

    arr = _to_arr(img)
    h, s, l = _rgb_to_hsl(arr)
    h = (h + amount / 360.0) % 1.0
    return Image.fromarray(_hsl_to_rgb(h, s, l))


# ---------------------------------------------------------------------------
# Effect: Chromatic Aberration
# ---------------------------------------------------------------------------

def apply_chromatic_aberration(img, params):
    """Offset R right, B left."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img)
    offset = amount // 2
    out = arr.copy()
    out[:,:,0] = np.roll(arr[:,:,0], offset, axis=1)   # R right
    out[:,:,2] = np.roll(arr[:,:,2], -offset, axis=1)  # B left
    return _to_img(out)


# ---------------------------------------------------------------------------
# Effect: Edge Corruption
# ---------------------------------------------------------------------------

def apply_edge_corruption(img, params):
    """Random pixels on image borders."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).copy()
    h, w = arr.shape[:2]
    border = 20

    Y = np.arange(h)[:, None]
    X = np.arange(w)
    on_border = (X < border) | (X >= w - border) | (Y < border) | (Y >= h - border)
    replace_mask = on_border & (_bulk_random(h, w) < amount / 100.0)
    replacement = np.random.randint(0, 256, size=(h, w, 3), dtype=np.uint8)
    arr[replace_mask] = replacement[replace_mask]
    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Digital Rain
# ---------------------------------------------------------------------------

def apply_digital_rain(img, params):
    """Green vertical streaks in 10px columns."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    h, w = arr.shape[:2]
    col_w = 10

    for cx in range(0, w, col_w):
        if random.random() < amount / 100.0:
            streak_y = random.randint(0, h - 1)
            streak_len = random.randint(20, max(20, min(80, h - streak_y)))
            y0 = streak_y
            y1 = min(streak_y + streak_len, h)
            x0 = cx
            x1 = min(cx + col_w, w)
            actual_len = y1 - y0
            intensity = 1.0 - np.arange(actual_len) / streak_len
            inten = intensity[:, np.newaxis]
            arr[y0:y1, x0:x1, 1] += 200 * inten
            arr[y0:y1, x0:x1, 0] *= (1 - 0.3 * inten)
            arr[y0:y1, x0:x1, 2] *= (1 - 0.3 * inten)

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Compression Artifacts
# ---------------------------------------------------------------------------

def apply_compression_artifacts(img, params):
    """8x8 block averaging."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).astype(np.float32)
    h, w = arr.shape[:2]
    blend = amount * 0.7 / 100.0

    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            if random.random() < amount * 0.3 / 100.0:
                cx = min(bx + 4, w - 1)
                cy = min(by + 4, h - 1)
                y1 = min(by + 8, h)
                x1 = min(bx + 8, w)
                cr, cg, cb = arr[cy, cx]
                arr[by:y1, bx:x1, 0] += (cr - arr[by:y1, bx:x1, 0]) * blend
                arr[by:y1, bx:x1, 1] += (cg - arr[by:y1, bx:x1, 1]) * blend
                arr[by:y1, bx:x1, 2] += (cb - arr[by:y1, bx:x1, 2]) * blend

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect: Channel Shift
# ---------------------------------------------------------------------------

def apply_channel_shift(img, params):
    """Radial R/G/B offsets from center."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img)
    h, w = arr.shape[:2]
    Y = np.arange(h, dtype=np.float32)[:, None]
    X = np.arange(w, dtype=np.float32)[None, :]
    cx, cy = w / 2.0, h / 2.0
    red_ox = ((X - cx) * amount * 0.005).astype(np.int32)
    green_oy = ((Y - cy) * amount * 0.005).astype(np.int32)
    blue_ox = ((cx - X) * amount * 0.005).astype(np.int32)
    r = arr[np.clip(Y, 0, h-1).astype(int), np.clip(X + red_ox, 0, w-1).astype(int), 0]
    g = arr[np.clip(Y + green_oy, 0, h-1).astype(int), np.clip(X, 0, w-1).astype(int), 1]
    b = arr[np.clip(Y, 0, h-1).astype(int), np.clip(X + blue_ox, 0, w-1).astype(int), 2]
    out = np.stack([r, g, b], axis=-1)
    return _to_img(out)


# ---------------------------------------------------------------------------
# Effect: Buffer Overflow
# ---------------------------------------------------------------------------

def apply_buffer_overflow(img, params):
    """Copy random source lines to random target lines."""
    amount = params.get("amount", 0)

    if amount <= 0:
        return img.copy()

    arr = _to_arr(img).copy()
    h, w = arr.shape[:2]
    num_lines = int(amount / 100.0 * h * 0.3)

    for _ in range(num_lines):
        src_y = random.randint(0, h - 1)
        dst_y = random.randint(0, h - 1)
        arr[dst_y] = arr[src_y].copy()
        # Add per-pixel noise to copied line
        noise_mask = _bulk_random(1, w).flatten() < amount / 100.0 * 0.5
        noise_vals = np.random.randint(-50, 51, size=(w, 3), dtype=np.int32)
        arr[dst_y, noise_mask] = np.clip(
            arr[dst_y, noise_mask].astype(np.int32) + noise_vals[noise_mask], 0, 255
        ).astype(np.uint8)

    return _to_img(arr)


# ---------------------------------------------------------------------------
# Effect registry and defaults
# ---------------------------------------------------------------------------

EFFECTS = {
    "rgbShift": rgb_shift,
    "noise": apply_noise,
    "scanLines": apply_scan_lines,
    "interference": apply_interference,
    "hShake": apply_h_shake,
    "vShake": apply_v_shake,
    "blockDistort": apply_block_distort,
    "waveDistort": apply_wave_distort,
    "pixelSort": apply_pixel_sort,
    "dataMosaic": apply_data_mosaic,
    "contrast": apply_contrast,
    "brightness": apply_brightness,
    "saturation": apply_saturation,
    "grayscale": apply_grayscale,
    "sepia": apply_sepia,
    "vintage": apply_vintage,
    "invert": apply_invert,
    "colorShift": apply_color_shift,
    "chromaticAberration": apply_chromatic_aberration,
    "edgeCorruption": apply_edge_corruption,
    "digitalRain": apply_digital_rain,
    "compressionArtifacts": apply_compression_artifacts,
    "channelShift": apply_channel_shift,
    "bufferOverflow": apply_buffer_overflow,
}
