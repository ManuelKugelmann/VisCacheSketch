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
            # `count` is the *hit* count (only incremented when a cache entry was
            # found). `coldmiss_rate = miss / total`. Reconstruct total queries:
            #   - Hits present (coldmiss_rate < 1): total = count / (1 − coldmiss_rate)
            #   - Fully cold (count=0, coldmiss_rate>0): pixel was queried but every
            #     lookup missed. We can't recover the exact total without a
            #     dedicated counter, so assume "queried every frame" (the common
            #     case for a persistently-cold cell). Must NOT exclude these
            #     pixels from the mask — they're real data, not empty.
            #   - Never queried (both zero): skipped pixel (sky / letterbox).
            never_queried = (count == 0) & (coldmiss_rate == 0)
            fully_cold    = (count == 0) & (coldmiss_rate > 0)
            hit_rate = np.clip(1.0 - coldmiss_rate, 1e-7, 1.0)
            total_queries = count / hit_rate
            total_queries[fully_cold]    = float(total_frames) if total_frames else 1.0
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


def _min_filter_2d(img, size):
    """Local minimum over a size×size window (size must be odd, ≥3).
    Used for morphological erosion of error maps: the result at each pixel
    is the smallest value in its neighborhood, so the global max-of-min is
    'the highest err value such that every pixel in some size×size window
    is at least that high'. Single-pixel outliers vanish (their min over
    the window is some surrounding low value); sustained clusters survive.
    """
    if size < 3:
        return img.astype(np.float32, copy=False)
    radius = size // 2
    src = img.astype(np.float32, copy=False)
    pad = np.pad(src, radius, mode="edge")
    H, W = src.shape
    out = pad[radius:radius+H, radius:radius+W].copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx == 0:
                continue
            np.minimum(out, pad[radius+dy:radius+dy+H, radius+dx:radius+dx+W], out=out)
    return out


def _gaussian_blur_2d(img, sigma):
    """Separable 1D Gaussian, numpy-only. `img` can be (H,W) or (H,W,C)."""
    if sigma <= 0:
        return img.astype(np.float32, copy=False)
    radius = max(1, int(np.ceil(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    k /= k.sum()
    src = img.astype(np.float32, copy=False)
    # Pad with edge replication to avoid darkening at borders.
    if src.ndim == 2:
        pad = np.pad(src, radius, mode="edge")
        # Horizontal
        tmp = np.zeros_like(src)
        for i, ki in enumerate(k):
            tmp += ki * pad[radius:radius+src.shape[0], i:i+src.shape[1]]
        # Vertical
        pad2 = np.pad(tmp, radius, mode="edge")
        out = np.zeros_like(src)
        for i, ki in enumerate(k):
            out += ki * pad2[i:i+src.shape[0], radius:radius+src.shape[1]]
        return out
    # (H,W,C): blur each channel
    out = np.empty_like(src)
    for c in range(src.shape[2]):
        out[..., c] = _gaussian_blur_2d(src[..., c], sigma)
    return out


# Structural-error parameters. σ matches the tile-scale (16 px); a smaller
# smoothing kernel preserves block-pattern sharpness so cold-start hatches
# don't get smeared across neighboring tiles. pixel_weight is bumped so the
# per-pixel ΔE inside an artefact block contributes more visibly to the
# composite — pure smoothing alone was masking small-magnitude block patterns.
STRUCTURAL_SIGMA = 4.0
STRUCTURAL_PIXEL_WEIGHT = 0.5


# Luminance floor for CoV denominator. Below this the noise metric switches
# from relative (std/lum) to near-absolute — true black areas no longer
# saturate to "maximum noise" just because the signal is near zero.
# 0.02 ≈ 2% sRGB luminance; anything darker than that and divide-by-near-zero
# takes over. The blend is smooth (sqrt(lum² + floor²)) so well-lit regions
# see unchanged CoV and shadow tone-mapped regions get a stable floor.
_NOISE_LUM_FLOOR = 0.02


def _bilateral_noise_map(img_rgb, radius=2, phi=0.1):
    """Per-pixel bilateral-variance coefficient of variation for sRGB [0,1] (H,W,3).
    Edge-aware: luminance-weighted bilateral window suppresses edges. Returns (H,W) in [0,1].

    Uses a soft luminance floor so fully-black regions don't saturate the CoV
    metric (std/lum → ∞ as lum → 0). `std / sqrt(lum² + floor²)` keeps the
    relative-noise interpretation in lit areas and smoothly transitions to a
    stable low value as luminance approaches zero.
    """
    lum = 0.2126 * img_rgb[:, :, 0] + 0.7152 * img_rgb[:, :, 1] + 0.0722 * img_rgb[:, :, 2]
    h, w = lum.shape
    sum_w  = np.full((h, w), 1e-6, dtype=np.float32)
    sum_wl = np.zeros((h, w), dtype=np.float32)
    sum_wl2 = np.zeros((h, w), dtype=np.float32)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(np.roll(lum, -dy, axis=0), -dx, axis=1)
            weight = np.exp(-np.abs(lum - shifted) / max(phi, 1e-6))
            sum_w  += weight
            sum_wl += weight * shifted
            sum_wl2 += weight * shifted * shifted
    mean = sum_wl / sum_w
    var = np.maximum(0, sum_wl2 / sum_w - mean * mean)
    denom = np.sqrt(lum * lum + _NOISE_LUM_FLOOR * _NOISE_LUM_FLOOR)
    cov = np.sqrt(var) / denom
    return np.clip(cov, 0, 1).astype(np.float32)


def compute_render_noise(render_path, outpath, nodata=None, radius=2, phi=0.1, floor=None):
    """Absolute bilateral-noise map → viridis PNG.

    Bilateral-weighted CoV of luminance in a small window — edge-aware because
    bilateral weights collapse across luminance discontinuities, so the measure
    responds to stochastic grain, not to edges. Kept without the Gaussian pre-
    smooth used by the structural error metric: smoothing averages away the
    very high-frequency signal that `noise` is meant to detect.

    floor: optional (H,W) float32 noise map (e.g. bilateral_noise of the
    converged x4096 GT). Subtracted from the per-pixel bilateral noise before
    visualization so a self-reference plate (render == floor-source) renders
    as all-zero — calibrates out the residual noise that remains in the most
    converged render we have.

    Returns dict {mean_noise, mean_noise_pct}. Noise is already a per-pixel
    bilateral CoV — no blob smoothing, no windowed-max. The "correlated hot
    spot" story belongs to the error metric, not the noise metric.
    """
    img = np.array(Image.open(render_path)).astype(np.float32) / 255.0
    noise = _bilateral_noise_map(img[:, :, :3], radius=radius, phi=phi)
    if floor is not None and floor.shape == noise.shape:
        noise = np.maximum(noise - floor, 0.0)
    viridis_png(noise, outpath, nodata=nodata)
    mask = _valid_mask_from_nodata(nodata, noise.shape)
    s = _map_stats(noise, mask=mask, blob_sigma=None, norm=1.0)
    return {
        "mean_noise":     s["mean"],
        "mean_noise_pct": s["mean_pct"],
    }


def bilateral_noise_cached(render_path, cache_path=None, radius=2, phi=0.1):
    """Bilateral-noise map of a single tonemapped PNG, with optional .npy cache.
    Used to compute and persist the "self-noise" of a converged reference
    (x4096 GT). The cached map gets subtracted from lower-SPP / variant noise
    plates via the `floor` param of compute_render_noise / *_signed.
    """
    if cache_path and os.path.exists(cache_path):
        try:
            return np.load(cache_path).astype(np.float32)
        except (IOError, OSError, ValueError):
            pass
    try:
        img = np.array(Image.open(render_path)).astype(np.float32) / 255.0
    except (IOError, OSError):
        return None
    noise = _bilateral_noise_map(img[:, :, :3], radius=radius, phi=phi)
    if cache_path:
        try:
            np.save(cache_path, noise)
        except (IOError, OSError):
            pass
    return noise


def compute_render_noise_signed(render_path, baseline_path, outpath, nodata=None, radius=2, phi=0.1):
    """Absolute bilateral noise of the render — noise(render) only, no
    subtraction of baseline noise. Independent of vanilla's per-SPP noise
    pattern. Baseline path retained in signature for compat; baseline noise
    is computed and reported separately for side-by-side comparison.

    Returns dict {noise_vis_mean, noise_van_mean, noise_delta_*} where the
    "delta" field names are kept for CSV/plot pipeline compat but contain
    absolute noise(render) numbers, always >= 0.
    """
    try:
        img_r = np.array(Image.open(render_path)).astype(np.float32) / 255.0
        img_b = np.array(Image.open(baseline_path)).astype(np.float32) / 255.0
    except (IOError, OSError):
        return None
    if img_r.shape[:2] != img_b.shape[:2]:
        return None
    n_r = _bilateral_noise_map(img_r[:, :, :3], radius=radius, phi=phi)
    n_b = _bilateral_noise_map(img_b[:, :, :3], radius=radius, phi=phi)
    denom  = 1.0
    # Absolute noise PNG (viridis 0 to denom). No signed bipolar — n_r is
    # non-negative. Vanilla noise written to <name>.vanilla.png for compare.
    viridis_png(np.clip(n_r / denom, 0.0, 1.0), outpath, nodata=nodata)
    if outpath.endswith(".png"):
        van_path = outpath.replace(".png", ".vanilla.png")
    else:
        van_path = outpath + ".vanilla"
    viridis_png(np.clip(n_b / denom, 0.0, 1.0), van_path, nodata=nodata)
    mask = _valid_mask_from_nodata(nodata, n_r.shape)
    if not mask.any():
        mask = np.ones_like(mask)
    vals = n_r[mask]
    n_vis  = float(np.nanmean(vals))
    n_van  = float(np.nanmean(n_b[mask]))
    s_m    = n_vis  # absolute, NOT a delta
    s_min  = float(np.nanpercentile(vals, 1))
    s_max  = float(np.nanpercentile(vals, 99))
    # Absolute noise blob — max smoothed cache noise. Independent of vanilla.
    blur = _gaussian_blur_2d(n_r, NOISE_BLOB_SIGMA)
    bvals = np.where(mask, blur, np.nan)
    try:
        blob_peak = float(np.nanmax(bvals))
    except (ValueError, RuntimeWarning):
        blob_peak = 0.0
    blob_pct = 100.0 * max(0.0, blob_peak) / max(denom, 1e-6)
    return {
        "noise_vis_mean":       n_vis,
        "noise_van_mean":       n_van,
        "noise_delta_mean":     s_m,
        "noise_delta_min":      s_min,
        "noise_delta_max":      s_max,
        "noise_delta_pct":      100.0 * s_m   / denom,
        "noise_delta_min_pct":  100.0 * s_min / denom,
        "noise_delta_max_pct":  100.0 * s_max / denom,
        "noise_delta_blob_pct": blob_pct,
    }


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


def _reinhard_tone_map(c):
    """HDR → [0,1) Reinhard: x / (1+x). Perceptual compression of highlights
    so error metrics don't get dominated by bright HDR regions (e.g. Sponza
    sun-lit floor). Linear in the toe, log-like in the shoulder.

    Robust to NaN / ±inf: NaN → 0, +inf → +1, −inf → −1. Path-traced HDR
    can contain firefly inf values (singular specular paths, division by
    near-zero pdf). Without this guard, ΔE becomes NaN and the entire
    blob/error metric collapses to 0 — the BistroInterior x1 reference
    failure mode.
    """
    finite = np.isfinite(c)
    c_safe = np.where(finite, c, 0.0)
    out = c_safe / (1.0 + np.abs(c_safe))
    # finite → out; +inf → +1; −inf → −1; NaN → 0
    inf_replacement = np.where(np.isnan(c), 0.0, np.sign(c))
    out = np.where(finite, out, inf_replacement)
    return out.astype(np.float32)


def _oklab_distance_hdr(a_exr, b_exr):
    """Structural perceptual error between two HDR EXRs — Gaussian-smoothed
    OkLab distance (2× L weight) plus a scaled per-pixel residual.

    Rationale: per-pixel ΔE is dominated by edge aliasing (a single jittered
    edge pixel has huge ΔE even if the image is otherwise correct). A
    Gaussian low-pass at the correlated-pattern scale (σ ≈ half tile width)
    averages edge jaggies to near-zero while preserving tile-scale bias
    patterns (cold-start artifacts, systematic over-skip by RR, etc.).
    Combined = ΔE_smoothed + STRUCTURAL_PIXEL_WEIGHT × ΔE_pixel keeps some
    sensitivity to truly localized errors (firefly bursts) without letting
    edge aliasing dominate.

    Returns (H, W) float32 or None on error."""
    a_data = read_exr(a_exr)
    b_data = read_exr(b_exr)
    a_lin = a_data.get("RGBA", a_data.get("RGB"))
    b_lin = b_data.get("RGBA", b_data.get("RGB"))
    if a_lin is None or b_lin is None or a_lin.shape[:2] != b_lin.shape[:2]:
        return None
    # Tone-map HDR values before OkLab distance so brightly-lit regions
    # (Sponza sun-lit floor) don't dominate the metric. Reinhard x/(1+x)
    # maps [0, inf) → [0, 1), compressing highlights perceptually. Without
    # this, a 10x brighter floor contributes 10x more L distance for the
    # same relative difference.
    a_ldr = _reinhard_tone_map(a_lin[:, :, :3])
    b_ldr = _reinhard_tone_map(b_lin[:, :, :3])

    # Pixel ΔE
    lab_a_p = _srgb_to_oklab(_linear_to_srgb(a_ldr))
    lab_b_p = _srgb_to_oklab(_linear_to_srgb(b_ldr))
    dL_p = lab_a_p[..., 0] - lab_b_p[..., 0]
    da_p = lab_a_p[..., 1] - lab_b_p[..., 1]
    db_p = lab_a_p[..., 2] - lab_b_p[..., 2]
    err_p = np.sqrt(4.0 * dL_p**2 + da_p**2 + db_p**2).astype(np.float32)

    # Structural ΔE: blur tone-mapped RGB (Gaussian symmetric in LDR space
    # after compression), then OkLab on the smoothed result.
    a_blur = _gaussian_blur_2d(a_ldr, STRUCTURAL_SIGMA)
    b_blur = _gaussian_blur_2d(b_ldr, STRUCTURAL_SIGMA)
    lab_a_s = _srgb_to_oklab(_linear_to_srgb(np.clip(a_blur, 0, 1)))
    lab_b_s = _srgb_to_oklab(_linear_to_srgb(np.clip(b_blur, 0, 1)))
    dL_s = lab_a_s[..., 0] - lab_b_s[..., 0]
    da_s = lab_a_s[..., 1] - lab_b_s[..., 1]
    db_s = lab_a_s[..., 2] - lab_b_s[..., 2]
    err_s = np.sqrt(4.0 * dL_s**2 + da_s**2 + db_s**2).astype(np.float32)

    return (err_s + STRUCTURAL_PIXEL_WEIGHT * err_p).astype(np.float32)


def oklab_distance_hdr_cached(a_exr, b_exr, cache_path=None):
    """Like _oklab_distance_hdr, but reads/writes a .npy cache if cache_path is given.
    Bad or missing cache falls through to recompute. Used to skip recomputing
    vanilla-vs-GT (same across variants) for every ladder variant."""
    if cache_path and os.path.exists(cache_path):
        try:
            return np.load(cache_path).astype(np.float32)
        except (IOError, OSError, ValueError):
            pass  # bad cache → fall through
    arr = _oklab_distance_hdr(a_exr, b_exr)
    if arr is not None and cache_path:
        try:
            np.save(cache_path, arr)
        except (IOError, OSError):
            pass
    return arr


def _signed_error_png(signed, outpath, nodata=None, norm=1.4):
    """Signed error PNG anchored at viridis(0) = dark purple.
    `signed` is (H,W) in units where ±norm is the clip range:
      positive → viridis ramp (purple → blue → green → yellow) as the delta grows
      zero     → viridis(0) = dark purple (parity with vanilla at same SPP)
      negative → purple → black ramp as the improvement grows (viridis(0) * (1 − |s|/norm))
    """
    s = np.clip(signed / max(norm, 1e-6), -1.0, 1.0).astype(np.float32)
    h, w = signed.shape
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    pos = s > 0
    neg = ~pos
    purple = np.array(cm.viridis(0.0)[:3], dtype=np.float32)
    if pos.any():
        rgb[pos] = cm.viridis(s[pos])[:, :3].astype(np.float32)
    if neg.any():
        factor = (1.0 + s[neg]).astype(np.float32)  # 1 at s=0 (purple), 0 at s=-1 (black)
        rgb[neg] = factor[:, np.newaxis] * purple[np.newaxis, :]
    if nodata is not None:
        cm_arr = np.asarray(nodata)
        if cm_arr.dtype == bool:
            rgb[cm_arr] = 0.0
        else:
            rgb *= np.clip(cm_arr, 0.0, 1.0)[:, :, np.newaxis]
    Image.fromarray((rgb * 255).astype(np.uint8)).save(outpath)


def _valid_mask_from_nodata(nodata, shape):
    """Resolve nodata argument to a boolean (H,W) mask of *valid* pixels.
    None or shape mismatch → all-True. Bool array → ~nodata. Float array → nodata > 0.5.
    """
    if nodata is None:
        return np.ones(shape, dtype=bool)
    arr = np.asarray(nodata)
    if arr.shape != shape:
        return np.ones(shape, dtype=bool)
    if arr.dtype == bool:
        return ~arr
    return arr > 0.5


def compute_render_error_signed_hdr(render_exr, vanilla_xN_exr, gt_exr, outpath, nodata=None,
                                     vanilla_err_cache=None):
    """Absolute HDR GT-error: OkLab(2×L) distance from render to x4096 GT.

    The metric is **noise-independent** — it does not subtract vanilla_xN's
    per-SPP sampling noise. err_pct and err_blob_pct are pure cache quality
    numbers vs GT; vanilla_err_pct / vanilla_err_blob_pct are vanilla's same
    numbers for side-by-side comparison.

    `vanilla_xN_exr` is retained in the signature for parallel viewing — its
    error map is computed separately and the deltas are reported alongside,
    but the primary `err_*_pct` outputs are absolute vs GT.

    Returns dict with mean stats, or None on failure. Field names kept for
    pipeline compatibility but **semantics changed**:
      err_vis_gt_mean:    mean OkLabDistance(viscache, GT) over valid pixels
      err_van_gt_mean:    mean OkLabDistance(vanilla_xN, GT) over valid pixels
      err_delta_mean:     err_vis_gt_mean (NOT a delta — absolute mean err vs GT)
      err_delta_pct:      100 × err_vis_gt_mean / 1.4 (% of OkLab max, always >=0)
      err_delta_min_pct:  100 × p1(err_vis_gt) / 1.4 (1st percentile)
      err_delta_max_pct:  100 × p99(err_vis_gt) / 1.4 (99th percentile)
      err_delta_blob_pct: 100 × max(smoothed(err_vis_gt)) / 1.4 (worst region vs GT)
      err_delta_blob_sum_pct: area-weighted blob magnitude vs GT
    """
    err_render  = _oklab_distance_hdr(render_exr, gt_exr)
    err_vanilla = oklab_distance_hdr_cached(vanilla_xN_exr, gt_exr, vanilla_err_cache)
    if err_render is None:
        print(f"[viscache_exr] WARNING: cannot compute HDR error (missing or mismatched inputs)")
        return None
    # Visualize absolute err map (viridis from 0 to denom) — replaces signed PNG.
    # Vanilla map written to a sibling path with .vanilla suffix for compare.
    mask = _valid_mask_from_nodata(nodata, err_render.shape)
    if not mask.any():
        mask = np.ones_like(mask)
    denom = 1.4
    viridis_png(np.clip(err_render / denom, 0.0, 1.0), outpath, nodata=nodata)
    if err_vanilla is not None and err_vanilla.shape == err_render.shape:
        van_path = outpath.replace(".png", ".vanilla.png") if outpath.endswith(".png") else outpath + ".vanilla"
        viridis_png(np.clip(err_vanilla / denom, 0.0, 1.0), van_path, nodata=nodata)

    vals = err_render[mask]
    err_vis  = float(np.nanmean(vals))
    err_van  = float(np.nanmean(err_vanilla[mask])) if err_vanilla is not None else None
    s_m      = err_vis  # "delta_mean" name kept; semantics is absolute mean err vs GT
    s_min    = float(np.nanpercentile(vals, 1))
    s_max    = float(np.nanpercentile(vals, 99))
    # Absolute-blob: max of Gaussian-blurred err_render (no signed clamping needed
    # since err is non-negative). Reports worst-region cache distance to GT,
    # independent of vanilla's per-SPP noise pattern.
    blur = _gaussian_blur_2d(err_render, ERR_WINDOW_SIGMA)
    bvals = np.where(mask, blur, np.nan)
    try:
        blob_peak = float(np.nanmax(bvals))
    except (ValueError, RuntimeWarning):
        blob_peak = 0.0
    blob_pct = 100.0 * max(0.0, blob_peak) / max(denom, 1e-6)
    blob_sum_pct = _signed_blob_sum_pct(err_render, mask, ERR_WINDOW_SIGMA, denom)

    # Cluster-blob: max err such that every pixel in a 5x5 neighborhood
    # also exceeds it. Single-pixel firefly noise is dropped; sustained
    # localized artifacts dominate. This is the "is this an artifact"
    # discriminator — preferred for hard-reject in the picker rule.
    cluster_eroded = _min_filter_2d(err_render, CLUSTER_BLOB_KERNEL)
    cmasked = np.where(mask, cluster_eroded, np.nan)
    try:
        cluster_peak = float(np.nanmax(cmasked))
    except (ValueError, RuntimeWarning):
        cluster_peak = 0.0
    cluster_blob_pct = 100.0 * max(0.0, cluster_peak) / max(denom, 1e-6)

    # Vanilla's same numbers — for side-by-side comparison at the same SPP.
    van_err_pct = None
    van_blob_pct = None
    van_cluster_blob_pct = None
    if err_vanilla is not None and err_vanilla.shape == err_render.shape:
        vvals = err_vanilla[mask]
        van_err_pct = 100.0 * float(np.nanmean(vvals)) / denom
        van_blur = _gaussian_blur_2d(err_vanilla, ERR_WINDOW_SIGMA)
        van_bvals = np.where(mask, van_blur, np.nan)
        try:
            van_blob_peak = float(np.nanmax(van_bvals))
        except (ValueError, RuntimeWarning):
            van_blob_peak = 0.0
        van_blob_pct = 100.0 * max(0.0, van_blob_peak) / max(denom, 1e-6)
        van_cluster = _min_filter_2d(err_vanilla, CLUSTER_BLOB_KERNEL)
        van_cmasked = np.where(mask, van_cluster, np.nan)
        try:
            van_cluster_peak = float(np.nanmax(van_cmasked))
        except (ValueError, RuntimeWarning):
            van_cluster_peak = 0.0
        van_cluster_blob_pct = 100.0 * max(0.0, van_cluster_peak) / max(denom, 1e-6)

    return {
        "err_vis_gt_mean":    err_vis,
        "err_van_gt_mean":    err_van,
        "err_delta_mean":     s_m,
        "err_delta_min":      s_min,
        "err_delta_max":      s_max,
        "err_delta_pct":      100.0 * s_m   / denom,
        "err_delta_min_pct":  100.0 * s_min / denom,
        "err_delta_max_pct":  100.0 * s_max / denom,
        "err_delta_blob_pct": blob_pct,
        "err_delta_blob_sum_pct": blob_sum_pct,
        # Cluster-blob: artifact discriminator. Max err where ALL pixels in
        # a 5x5 window exceed it. Localized clusters survive; scattered
        # firefly noise gets erased by the local min. Use as the hard-
        # reject signal for "this variant produces visible artifacts".
        "err_cluster_blob_pct": cluster_blob_pct,
        # Vanilla baseline at same SPP — side-by-side comparison vs GT, not subtracted.
        "vanilla_err_pct":      van_err_pct,
        "vanilla_err_blob_pct": van_blob_pct,
        "vanilla_err_cluster_blob_pct": van_cluster_blob_pct,
    }


# Gaussian σ for the "max-blob" windowed-max stat on correlated-error maps.
# ~σ×3 radius (~12 px) captures tile-scale hot spots (16 px tile) coherently.
ERR_WINDOW_SIGMA = 4.0

# Cluster-blob kernel: max err where every pixel in this window also
# exceeds it. 5x5 = 25 pixels — single firefly-like outliers don't survive
# (their neighborhood includes a low-err pixel and the min collapses);
# clusters of 25+ contiguous bad pixels do. The "this region is uniformly
# bad" detector — what users perceive as a visible artifact.
CLUSTER_BLOB_KERNEL = 5

# Larger window for the noise (firefly) blob — fireflies are single-pixel
# spikes whose bilateral-noise delta is very localized. A wider Gaussian
# smooths them into recognizable blobs and de-emphasizes isolated-pixel
# noise that doesn't represent a visual artifact cluster.
NOISE_BLOB_SIGMA = 12.0


def _signed_blob_pct(signed, mask, sigma, denom):
    """Positive-only max-blob stat for a correlated signed-error map.

    Reports the worst *degradation* blob — Gaussian-blurred max of the signed
    map, clamped at 0. Negative blobs (viscache denoised) are discarded; the
    stat is meant to surface "how bad does viscache get in the worst region"
    and negative means doesn't apply. Single-pixel outliers can't dominate.
    denom converts raw value to percentage.
    """
    blob = _gaussian_blur_2d(signed, sigma)
    b = np.where(mask, blob, np.nan)
    try:
        pos = float(np.nanmax(b))
    except (ValueError, RuntimeWarning):
        return None
    return 100.0 * max(0.0, pos) / max(denom, 1e-6)


def _signed_blob_sum_pct(signed, mask, sigma, denom, threshold_pct=2.0):
    """Area-fraction × mean magnitude of concentrated-artifact regions.

    blob_pct (above) is a single worst-case peak — a variant with one
    bad pixel and a variant with thousands of bad pixels both report the
    same value. blob_sum_pct reports the fraction of the image with
    blurred delta above `threshold_pct`, weighted by how far each pixel
    is over the threshold. Units: percentage-points, where 1.0 means
    "1% of the image is ~1pp over threshold".

    Use alongside blob_pct: max tells you peak severity; sum tells you
    how much of the image is affected.
    """
    blob = _gaussian_blur_2d(signed, sigma)
    b = np.where(mask, blob, np.nan)
    # Raw-to-pct factor matches blob_pct semantics
    raw = b / max(denom, 1e-6) * 100.0  # pct per pixel
    over = raw - threshold_pct
    over = np.where(np.isfinite(over) & (over > 0), over, 0.0)
    n_valid = int(np.count_nonzero(mask))
    if n_valid == 0:
        return 0.0
    # integrate the over-threshold "volume" then normalize by valid pixel count
    # gives: average pct-excess per valid pixel. If 5% of image is 3pp over
    # threshold → 0.05 × 3 = 0.15 pct-pt.
    return float(over.sum() / n_valid)


def _map_stats(arr, mask=None, blob_sigma=None, norm=1.0):
    """Mean + optional windowed-max stats of a per-pixel float map.

    arr:        (H,W) float32. mask: optional bool (H,W) — defaults to all True.
    blob_sigma: if > 0, `max` is taken over a Gaussian-smoothed copy so that a
                single-pixel outlier can't blow up the stat; the peak sits at
                the center of the worst correlated blob. If None, `max` is
                omitted from the result.
    norm:       divisor to convert raw values to percentage (e.g. 1.4 for
                OkLab max distance, 1.0 for bilateral noise).

    Returns dict with "mean", "mean_pct", and optionally "max", "max_pct".
    """
    if mask is None:
        mask = np.ones(arr.shape, dtype=bool)
    if not mask.any():
        mask = np.ones_like(mask)
    d = max(norm, 1e-6)
    mean_v = float(np.nanmean(arr[mask]))
    out = {"mean": mean_v, "mean_pct": 100.0 * mean_v / d}
    if blob_sigma is not None and blob_sigma > 0:
        blob  = _gaussian_blur_2d(arr, blob_sigma)
        max_v = float(np.nanmax(blob[mask]))
        out["max"]     = max_v
        out["max_pct"] = 100.0 * max_v / d
    return out


def compute_render_error_hdr(render_exr, baseline_exr, outpath, nodata=None,
                              distance_cache=None):
    """HDR perceptual error (OkLab, 2× L weight) from pre-tonemapper EXRs → viridis PNG.
    Converts linear HDR to sRGB before OkLab (OkLab expects sRGB input).
    Clamps negative values and fireflies before conversion.

    distance_cache: optional .npy path to reuse / populate the per-pixel OkLab
    distance map. Lets baseline GT-err generation seed a cache that the later
    signed-delta step for each variant then reads instead of recomputing.

    Returns dict {mean_err, mean_err_pct, max_err, max_err_pct} or None on failure.
      mean_err_pct = 100 × mean_err / 1.4                — mean intensity %
      max_err_pct  = 100 × max(gaussian_blur(err)) / 1.4 — worst-blob %.
                      σ=ERR_WINDOW_SIGMA so a single-pixel firefly can't
                      dominate; tracks the worst *region* of correlated error.
    """
    err = oklab_distance_hdr_cached(render_exr, baseline_exr, distance_cache)
    if err is None:
        print(f"[viscache_exr] WARNING: cannot read HDR EXR or shape mismatch, skipping error")
        return None
    viridis_png(np.clip(err / 1.4, 0, 1), outpath, nodata=nodata)
    mask = _valid_mask_from_nodata(nodata, err.shape)
    s = _map_stats(err, mask=mask, blob_sigma=ERR_WINDOW_SIGMA, norm=1.4)
    return {
        "mean_err":     s["mean"],
        "mean_err_pct": s["mean_pct"],
        "max_err":      s["max"],
        "max_err_pct":  s["max_pct"],
    }
