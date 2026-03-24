"""Test: read EXR diagnostic output, apply viridis colormap, blend coldmiss as black."""
import sys, os, glob
import numpy as np
import OpenEXR
import matplotlib.cm as cm
from PIL import Image

def read_exr(path):
    """Read EXR → dict of channel_group_name → (H,W,C) float32 numpy array."""
    f = OpenEXR.File(path)
    result = {}
    for key, ch in f.channels().items():
        result[key] = ch.pixels.astype(np.float32)
    return result

def viridis_png(data, outpath, coldmiss=None):
    """Apply viridis colormap to float data [0,1] and save as PNG.
    If coldmiss mask is provided (H,W bool), those pixels are rendered black.
    """
    rgb = cm.viridis(np.clip(data, 0.0, 1.0))[:, :, :3]
    if coldmiss is not None:
        rgb[coldmiss] = 0.0
    Image.fromarray((rgb * 255).astype(np.uint8)).save(outpath)

# --- Find test EXRs ---
capture_dir = sys.argv[1] if len(sys.argv) > 1 else "runtime/captures/debug"
out_dir = os.path.join(capture_dir, "pytest")
os.makedirs(out_dir, exist_ok=True)

exrs = glob.glob(os.path.join(capture_dir, "*.exr"))
if not exrs:
    print(f"No EXRs in {capture_dir}")
    sys.exit(1)

# Derive coldmiss mask from FrameMeanVarMatSamplesRaw: all RGB=0 means coldmiss
coldmiss_mask = None
for exr in exrs:
    if "FrameMeanVarMatSamplesRaw" in exr:
        channels = read_exr(exr)
        rgb = channels.get("RGB")
        if rgb is not None:
            coldmiss_mask = np.all(rgb == 0, axis=2)
            pct = coldmiss_mask.mean() * 100
            print(f"Coldmiss mask from {os.path.basename(exr)}: {pct:.1f}% cold")
        break

for exr in exrs:
    base = os.path.basename(exr)
    channels = read_exr(exr)
    rgb = channels.get("RGB")
    if rgb is None:
        continue

    is_frame = "Frame" in base or "Level" in base
    mask = coldmiss_mask if is_frame else None

    n_ch = rgb.shape[2] if len(rgb.shape) == 3 else 1
    tag = base.replace(".exr", "")

    for c in range(min(n_ch, 3)):
        ch_name = "RGB"[c]
        data = rgb[:, :, c] if n_ch > 1 else rgb
        stats = f"min={data.min():.4f} max={data.max():.4f} mean={data.mean():.4f}"
        outpath = os.path.join(out_dir, f"{tag}_{ch_name}.png")
        viridis_png(data, outpath, coldmiss=mask)
        print(f"  {tag} {ch_name}: {stats} -> {os.path.basename(outpath)}")

print(f"\nDone — {out_dir}/")
