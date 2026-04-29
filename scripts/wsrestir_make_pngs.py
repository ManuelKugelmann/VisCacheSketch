"""Quick HDR-EXR → tonemapped-PNG converter for WS-ReSTIR test renders.

Reads runtime/captures/wsrestir_test/<variant>/<scene>/*.AccumulatePass.output.*.exr
and writes a sibling .png next to each via simple ACES tonemap.
"""
import os, sys, glob
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_exr import read_exr

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "runtime", "captures", "wsrestir_test")
ROOT = os.path.normpath(ROOT)

def aces_tonemap(rgb):
    a = 2.51; b = 0.03; c = 2.43; d = 0.59; e = 0.14
    return np.clip((rgb * (a * rgb + b)) / (rgb * (c * rgb + d) + e), 0.0, 1.0)

def encode_srgb(rgb):
    a = 0.055
    lo = 12.92 * rgb
    hi = (1 + a) * np.power(np.clip(rgb, 1e-9, None), 1.0 / 2.4) - a
    return np.where(rgb <= 0.0031308, lo, hi)

count = 0
for path in glob.glob(os.path.join(ROOT, "*", "*", "*.AccumulatePass.output.*.exr")):
    channels = read_exr(path)
    # read_exr returns {group_name: (H,W,C) array}; pick first non-empty group.
    if not channels:
        print(f"  SKIP (corrupt): {path}")
        continue
    arr = next(iter(channels.values()))
    if arr.ndim == 3 and arr.shape[2] >= 3:
        rgb = arr[..., :3]
    elif arr.ndim == 2:
        rgb = np.stack([arr] * 3, axis=-1)
    else:
        rgb = arr
    rgb = np.maximum(rgb, 0)
    tm = encode_srgb(aces_tonemap(rgb))
    img = (np.clip(tm, 0, 1) * 255).astype(np.uint8)
    out = path.replace(".exr", ".png")
    Image.fromarray(img).save(out)
    print(f"  {os.path.relpath(out, ROOT)}")
    count += 1

print(f"Wrote {count} PNGs.")
