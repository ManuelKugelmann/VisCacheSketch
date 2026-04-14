"""viscache_exr.py — Low-level EXR → viridis PNG extraction for VisCache.

Single-channel utility. Drop-in for ladder scripts and other consumers.

    from viscache_exr import write_channel, load_nodata_mask, find_exr
    mask = load_nodata_mask(exr_list)
    write_channel("test.exr", 2, "mean.png", nodata=mask)

Requires: numpy, matplotlib, Pillow, OpenEXR.
"""
import os, glob
import numpy as np
import OpenEXR
import matplotlib.cm as cm
from PIL import Image


def read_exr(path):
    """Read EXR file → dict mapping group name ('RGB' or 'RGBA') to (H,W,C) float32 array.
    Retries once on corrupt data (GPU readback may still be in flight).
    """
    import time
    for attempt in range(2):
        try:
            f = OpenEXR.File(path)
            return {k: v.pixels.astype(np.float32) for k, v in f.channels().items()}
        except RuntimeError:
            if attempt == 0:
                time.sleep(0.1)
            else:
                print(f"[viscache_exr] WARNING: corrupt EXR, skipping: {os.path.basename(path)}")
                return {}


def viridis_png(data, outpath, nodata=None):
    """Apply viridis colormap to float [0,1] data and save as PNG.
    nodata: optional (H,W) array — bool mask (True=black) or float [0,1]
              alpha (0=black, 1=full color) for gradual darkening.
    """
    rgb = cm.viridis(np.clip(data, 0.0, 1.0))[:, :, :3]
    if nodata is not None:
        cm_arr = np.asarray(nodata)
        if cm_arr.dtype == bool:
            rgb[cm_arr] = 0.0
        else:
            # Float alpha: 0=black, 1=full viridis
            rgb *= np.clip(cm_arr, 0.0, 1.0)[:, :, np.newaxis]
    Image.fromarray((rgb * 255).astype(np.uint8)).save(outpath)


def write_channel(exr_path, channel_index, outpath, nodata=None, normalize_max=False):
    """Extract one channel from an EXR, apply viridis, save as PNG.

    Args:
        exr_path:       path to EXR file
        channel_index:  0=R, 1=G, 2=B, 3=A
        outpath:        output PNG path
        nodata:       optional (H,W) bool mask for black overlay
        normalize_max:  if True, divide by channel max before colormap (for unbounded data)

    Returns: outpath on success, None if channel not available.
    """
    data_dict = read_exr(exr_path)
    data = data_dict.get("RGBA", data_dict.get("RGB"))
    if data is None:
        return None
    n_ch = data.shape[2] if len(data.shape) == 3 else 1
    if channel_index >= n_ch:
        return None

    ch = data[:, :, channel_index] if n_ch > 1 else data
    if normalize_max:
        mx = ch.max()
        if mx > 0:
            ch = ch / mx

    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    viridis_png(ch, outpath, nodata=nodata)
    return outpath


def find_exr(exrs, substring):
    """Find first EXR path whose basename contains substring."""
    for exr in exrs:
        if substring in os.path.basename(exr):
            return exr
    return None


def load_diag_mask(exrs, mode="nodata", total_frames=None):
    """Load per-pixel nodata mask. Returns (H,W) float32 alpha: 0=black, 1=full color.

    Modes:
      "nodata":       accum — fractional if total_frames given, binary otherwise.
                      count (AccumMeanVarMatCount.A) = frames with cache hit.
                      coldmissRate (AccumRaysNoiseErrorCold.A) = 1 - hits/queries.
                      total queries = count / (1 - coldmissRate).
                      Never queried: count==0 && coldmissRate==0.
      "nodata_frame": frame — binary, from FrameHashAHashBHashABRays R+G both zero
                      (hash is never zero for queried pixels).
    """
    if mode == "nodata":
        count = None
        coldmiss_rate = None

        exr = find_exr(exrs, "AccumMeanVarMatCount")
        if exr:
            data = read_exr(exr).get("RGBA")
            if data is not None and data.shape[2] >= 4:
                count = data[:, :, 3]

        exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
        if exr:
            data = read_exr(exr).get("RGBA")
            if data is not None and data.shape[2] >= 4:
                coldmiss_rate = data[:, :, 3]

        if count is not None and coldmiss_rate is not None:
            hit_rate = np.clip(1.0 - coldmiss_rate, 1e-7, 1.0)
            total_queries = count / hit_rate
            never_queried = (count == 0) & (coldmiss_rate == 0)
            total_queries[never_queried] = 0.0

            if total_frames is not None and total_frames > 0:
                return np.clip(total_queries / float(total_frames), 0.0, 1.0).astype(np.float32)
            else:
                return np.where(never_queried, 0.0, 1.0).astype(np.float32)

        return load_diag_mask(exrs, mode="nodata_frame")

    if mode == "nodata_frame":
        exr = find_exr(exrs, "FrameHashAHashBHashABRays")
        if exr:
            data = read_exr(exr).get("RGBA", read_exr(exr).get("RGB"))
            if data is not None and data.shape[2] >= 2:
                no_data = (data[:, :, 0] == 0) & (data[:, :, 1] == 0)
                return np.where(no_data, 0.0, 1.0).astype(np.float32)
        return None


def compute_render_noise(render_path, outpath, nodata=None, radius=2, phi=0.1):
    """Bilateral luminance variance → coefficient of variation → viridis PNG.
    Edge-aware: luminance-weighted bilateral window suppresses edges.
    """
    img = np.array(Image.open(render_path)).astype(np.float32) / 255.0
    lum = 0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2]
    h, w = lum.shape

    sum_w = np.full((h, w), 1e-6, dtype=np.float32)
    sum_wl = np.zeros((h, w), dtype=np.float32)
    sum_wl2 = np.zeros((h, w), dtype=np.float32)

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(np.roll(lum, -dy, axis=0), -dx, axis=1)
            weight = np.exp(-np.abs(lum - shifted) / max(phi, 1e-6))
            sum_w += weight
            sum_wl += weight * shifted
            sum_wl2 += weight * shifted * shifted

    mean = sum_wl / sum_w
    var = np.maximum(0, sum_wl2 / sum_w - mean * mean)
    cov = np.sqrt(var) / np.maximum(lum, 1e-3)
    viridis_png(np.clip(cov, 0, 1), outpath, nodata=nodata)
    return outpath


def _srgb_to_oklab(img):
    """sRGB (H,W,3) float32 [0,1] → Oklab (H,W,3) as (L, a, b)."""
    lin = np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4).astype(np.float32)
    M1 = np.float32([[0.4122214708, 0.5363325363, 0.0514459929],
                      [0.2119034982, 0.6806995451, 0.1073969566],
                      [0.0883024619, 0.2024326433, 0.7092648948]])
    lms = lin @ M1.T
    lms_ = np.sign(lms) * np.abs(lms) ** (1.0 / 3.0)
    M2 = np.float32([[ 0.2104542553,  0.7936177850, -0.0040720468],
                      [ 1.9779984951, -2.4285922050,  0.4505937099],
                      [ 0.0259040371,  0.7827717662, -0.8086757660]])
    return (lms_ @ M2.T).astype(np.float32)


def compute_render_error(render_path, baseline_path, outpath, nodata=None):
    """Perceptual error (OkLab, 2x L weight) → viridis PNG.
    error = sqrt(4*dL² + da² + db²), normalized to [0,1].
    """
    img = np.array(Image.open(render_path)).astype(np.float32) / 255.0
    base = np.array(Image.open(baseline_path)).astype(np.float32) / 255.0
    if img.shape[:2] != base.shape[:2]:
        print(f"[viscache_exr] WARNING: shape mismatch, skipping error")
        return None
    lab1 = _srgb_to_oklab(img[:, :, :3])
    lab2 = _srgb_to_oklab(base[:, :, :3])
    dL = lab1[..., 0] - lab2[..., 0]
    da = lab1[..., 1] - lab2[..., 1]
    db = lab1[..., 2] - lab2[..., 2]
    err = np.sqrt(4.0 * dL**2 + da**2 + db**2)
    viridis_png(np.clip(err / 1.4, 0, 1), outpath, nodata=nodata)
    return outpath


def _linear_to_srgb(c):
    """Linear RGB → sRGB [0,1] for OkLab input."""
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.abs(c) ** (1.0/2.4) - 0.055).astype(np.float32)


def _oklab_distance_hdr(a_exr, b_exr):
    """Per-pixel OkLab perceptual distance (2× L weight) between two HDR EXRs.
    Returns (H, W) float32 or None on error. Clamps to [0, 10] pre-tonemap to
    suppress fireflies before sRGB conversion."""
    a_data = read_exr(a_exr)
    b_data = read_exr(b_exr)
    a_lin = a_data.get("RGBA", a_data.get("RGB"))
    b_lin = b_data.get("RGBA", b_data.get("RGB"))
    if a_lin is None or b_lin is None or a_lin.shape[:2] != b_lin.shape[:2]:
        return None
    a_lin = np.clip(a_lin[:, :, :3], 0, 10)
    b_lin = np.clip(b_lin[:, :, :3], 0, 10)
    lab_a = _srgb_to_oklab(_linear_to_srgb(a_lin))
    lab_b = _srgb_to_oklab(_linear_to_srgb(b_lin))
    dL = lab_a[..., 0] - lab_b[..., 0]
    da = lab_a[..., 1] - lab_b[..., 1]
    db = lab_a[..., 2] - lab_b[..., 2]
    return np.sqrt(4.0 * dL**2 + da**2 + db**2)


def _signed_error_png(signed, outpath, nodata=None, norm=1.4):
    """Signed error PNG anchored at viridis(0) = dark purple.
    `signed` is (H,W) in units where ±norm is the clip range:
      positive → viridis ramp (purple → blue → green → yellow) as degradation grows
      zero     → viridis(0) = dark purple (parity with vanilla at same SPP)
      negative → purple → black ramp as denoising gain grows (viridis(0) * (1 − |s|/norm))
    The result is a continuous, monotone scalar field: darker-than-purple = better,
    brighter-than-purple = worse.
    """
    s = np.clip(signed / max(norm, 1e-6), -1.0, 1.0).astype(np.float32)
    h, w = signed.shape
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    pos = s > 0
    neg = ~pos  # includes zero → viridis(0) naturally via 1 + s = 1
    purple = np.array(cm.viridis(0.0)[:3], dtype=np.float32)  # viridis's dark-purple anchor
    if pos.any():
        rgb[pos] = cm.viridis(s[pos])[:, :3].astype(np.float32)
    if neg.any():
        # factor in [0, 1]: 1 at s=0 (purple), 0 at s=-1 (black)
        factor = (1.0 + s[neg]).astype(np.float32)
        rgb[neg] = factor[:, np.newaxis] * purple[np.newaxis, :]
    if nodata is not None:
        cm_arr = np.asarray(nodata)
        if cm_arr.dtype == bool:
            rgb[cm_arr] = 0.0
        else:
            rgb *= np.clip(cm_arr, 0.0, 1.0)[:, :, np.newaxis]
    Image.fromarray((rgb * 255).astype(np.uint8)).save(outpath)


def compute_render_error_signed_hdr(render_exr, vanilla_xN_exr, gt_exr, outpath, nodata=None):
    """Signed HDR GT-error delta: err(render, GT) − err(vanilla_xN, GT) in OkLab (2× L).
    Negative (purple) = VisCache denoised at this SPP; positive (yellow) = VisCache degraded.
    Both errors use identical clamping + OkLab metric so the delta is unit-consistent.
    """
    err_render  = _oklab_distance_hdr(render_exr,  gt_exr)
    err_vanilla = _oklab_distance_hdr(vanilla_xN_exr, gt_exr)
    if err_render is None or err_vanilla is None:
        print(f"[viscache_exr] WARNING: cannot compute signed HDR error (missing or mismatched inputs)")
        return None
    if err_render.shape != err_vanilla.shape:
        print(f"[viscache_exr] WARNING: err shape mismatch, skipping signed error")
        return None
    _signed_error_png(err_render - err_vanilla, outpath, nodata=nodata)
    return outpath


def compute_render_error_hdr(render_exr, baseline_exr, outpath, nodata=None):
    """HDR perceptual error (OkLab, 2x L weight) from pre-tonemapper EXRs → viridis PNG.
    Converts linear HDR to sRGB before OkLab (OkLab expects sRGB input).
    Clamps negative values and fireflies before conversion.
    """
    render_data = read_exr(render_exr)
    base_data = read_exr(baseline_exr)
    img_lin = render_data.get("RGBA", render_data.get("RGB"))
    base_lin = base_data.get("RGBA", base_data.get("RGB"))
    if img_lin is None or base_lin is None:
        print(f"[viscache_exr] WARNING: cannot read HDR EXR, skipping error")
        return None
    if img_lin.shape[:2] != base_lin.shape[:2]:
        print(f"[viscache_exr] WARNING: HDR shape mismatch, skipping error")
        return None
    # Clamp to [0, 10] to suppress fireflies before tonemapping
    img_lin = np.clip(img_lin[:, :, :3], 0, 10)
    base_lin = np.clip(base_lin[:, :, :3], 0, 10)
    # Linear → sRGB → OkLab
    img_srgb = _linear_to_srgb(img_lin)
    base_srgb = _linear_to_srgb(base_lin)
    lab1 = _srgb_to_oklab(img_srgb)
    lab2 = _srgb_to_oklab(base_srgb)
    dL = lab1[..., 0] - lab2[..., 0]
    da = lab1[..., 1] - lab2[..., 1]
    db = lab1[..., 2] - lab2[..., 2]
    err = np.sqrt(4.0 * dL**2 + da**2 + db**2)
    viridis_png(np.clip(err / 1.4, 0, 1), outpath, nodata=nodata)
    return outpath
