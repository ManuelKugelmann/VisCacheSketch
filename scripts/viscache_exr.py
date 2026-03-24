"""viscache_exr.py — Low-level EXR → viridis PNG extraction for VisCache.

Single-channel utility. Drop-in for ladder scripts and other consumers.

    from viscache_exr import write_channel, load_coldmiss_mask, find_exr
    mask = load_coldmiss_mask(exr_list)
    write_channel("test.exr", 2, "mean.png", coldmiss=mask)

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


def viridis_png(data, outpath, coldmiss=None):
    """Apply viridis colormap to float [0,1] data and save as PNG.
    coldmiss: optional (H,W) array — bool mask (True=black) or float [0,1]
              alpha (0=black, 1=full color) for gradual darkening.
    """
    rgb = cm.viridis(np.clip(data, 0.0, 1.0))[:, :, :3]
    if coldmiss is not None:
        cm_arr = np.asarray(coldmiss)
        if cm_arr.dtype == bool:
            rgb[cm_arr] = 0.0
        else:
            # Float alpha: 0=black, 1=full viridis
            rgb *= np.clip(cm_arr, 0.0, 1.0)[:, :, np.newaxis]
    Image.fromarray((rgb * 255).astype(np.uint8)).save(outpath)


def write_channel(exr_path, channel_index, outpath, coldmiss=None, normalize_max=False):
    """Extract one channel from an EXR, apply viridis, save as PNG.

    Args:
        exr_path:       path to EXR file
        channel_index:  0=R, 1=G, 2=B, 3=A
        outpath:        output PNG path
        coldmiss:       optional (H,W) bool mask for black overlay
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
    viridis_png(ch, outpath, coldmiss=coldmiss)
    return outpath


def find_exr(exrs, substring):
    """Find first EXR path whose basename contains substring."""
    for exr in exrs:
        if substring in os.path.basename(exr):
            return exr
    return None


def load_coldmiss_mask(exrs, mode="frame"):
    """Load coldmiss mask from diagnostic EXRs.

    mode="frame":  per-frame bool mask from FrameLevelProbesSamplesCold.A
                   (True = no cache entry this frame). Returns (H,W) bool.
    mode="accum":  gradual float mask: 1 - coldmissRate [0,1].
                   0 = never hit (fully black), 1 = hit every frame (full color).
                   Uses AccumRaysNoiseErrorCold.A (accumulated cold miss rate).
                   Returns (H,W) float32.

    Returns mask array or None if data not available.
    """
    if mode == "accum":
        # AccumRaysNoiseErrorCold.A = accumColdmissRate [0,1] (computed in shader)
        exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
        if exr:
            channels = read_exr(exr)
            data = channels.get("RGBA")
            if data is not None and data.shape[2] >= 4:
                coldmiss_rate = data[:, :, 3]  # A channel
                return np.clip(1.0 - coldmiss_rate, 0.0, 1.0).astype(np.float32)  # hit rate as alpha
        return None

    # mode == "frame" — binary mask from FrameLevelProbesSamplesCold.A
    exr = find_exr(exrs, "FrameLevelProbesSamplesCold")
    if exr:
        channels = read_exr(exr)
        data = channels.get("RGBA")
        if data is not None and data.shape[2] >= 4:
            return data[:, :, 3] > 0.5

    # Fallback: FrameMeanVarMatSamplesRaw RGB==0
    exr = find_exr(exrs, "FrameMeanVarMatSamplesRaw")
    if exr:
        channels = read_exr(exr)
        data = channels.get("RGBA", channels.get("RGB"))
        if data is not None:
            return np.all(data[:, :, :3] == 0, axis=2)

    return None
