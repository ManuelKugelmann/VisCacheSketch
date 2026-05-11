"""
make_sponza_r3d_compare.py - paper-ready 2-up comparison plate for the
R3d Sponza firefly-cleanup finding (Step RPT_ZOO).

Reads existing RPT_ZOO captures (R2d and R3d at b=4 x16 on Sponza) and
emits a side-by-side tone-mapped PNG showing the firefly pathology
side-by-side: R2d on the left (DQLin's per-pixel reservoir produces
unbounded brightness spikes), R3d on the right (cell-pool first-writer-
wins suppresses the spikes).

Output: docs/devlog/plates/sponza_r3d_firefly_cleanup.png

Optionally falls back to whatever capture is most recent if the
specific filename isn't present (e.g. if SPP or BOUNCE differs).
"""
import os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import numpy as np

try:
    import OpenEXR, Imath
except ImportError:
    sys.exit("[plate] OpenEXR missing; runtime/pythondist/python.exe -m pip install OpenEXR")
try:
    from PIL import Image
except ImportError:
    sys.exit("[plate] Pillow missing; runtime/pythondist/python.exe -m pip install Pillow")


def load_exr_rgb(path):
    f = OpenEXR.InputFile(path)
    h = f.header(); dw = h["dataWindow"]
    w = dw.max.x - dw.min.x + 1
    H = dw.max.y - dw.min.y + 1
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    R = np.frombuffer(f.channel("R", pt), dtype=np.float32).reshape(H, w)
    G = np.frombuffer(f.channel("G", pt), dtype=np.float32).reshape(H, w)
    B = np.frombuffer(f.channel("B", pt), dtype=np.float32).reshape(H, w)
    return np.stack([R, G, B], axis=-1)


def tone_map(rgb):
    """Reinhard tone-map + clip non-finites + sRGB encode."""
    rgb = np.where(np.isfinite(rgb), np.maximum(rgb, 0.0), 0.0)
    tm = rgb / (1.0 + rgb)
    srgb = np.where(tm <= 0.0031308, 12.92 * tm, 1.055 * np.power(tm, 1.0 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255).astype(np.uint8)


def find_capture(variant_tag, scene="Sponza", spp=16, bounces=4):
    glob_pat = os.path.join(
        ROOT, "runtime", "captures", "ladder", "RPT_ZOO", scene,
        f"s_x{spp}_*_restirpt_{variant_tag}_b{bounces}_hdr.exr",
    )
    hits = sorted(glob.glob(glob_pat))
    if hits:
        return hits[0]
    # Fallback: any recent SPP for the variant.
    glob_pat = os.path.join(
        ROOT, "runtime", "captures", "ladder", "RPT_ZOO", scene,
        f"*_restirpt_{variant_tag}_b{bounces}_hdr.exr",
    )
    hits = sorted(glob.glob(glob_pat))
    return hits[-1] if hits else None


def main():
    r2d_exr = find_capture("R2d")
    r3d_exr = find_capture("R3d")
    if not r2d_exr or not r3d_exr:
        sys.exit(f"[plate] missing capture(s): R2d={r2d_exr}, R3d={r3d_exr}")
    print(f"[plate] R2d: {r2d_exr}")
    print(f"[plate] R3d: {r3d_exr}")

    r2d = load_exr_rgb(r2d_exr)
    r3d = load_exr_rgb(r3d_exr)

    r2d_max  = r2d[np.isfinite(r2d)].max() if np.isfinite(r2d).any() else 0.0
    r3d_max  = r3d.max() if np.isfinite(r3d).all() else 0.0
    r2d_fire = int((r2d > 100).any(-1).sum())
    r3d_fire = int((r3d > 100).any(-1).sum())
    print(f"[plate] R2d max={r2d_max:g}  fireflies (>100): {r2d_fire}")
    print(f"[plate] R3d max={r3d_max:g}  fireflies (>100): {r3d_fire}")

    r2d_png = tone_map(r2d)
    r3d_png = tone_map(r3d)
    H = max(r2d_png.shape[0], r3d_png.shape[0])
    W = r2d_png.shape[1] + r3d_png.shape[1]
    plate = np.zeros((H, W, 3), dtype=np.uint8)
    plate[: r2d_png.shape[0], : r2d_png.shape[1]] = r2d_png
    plate[: r3d_png.shape[0], r2d_png.shape[1] :] = r3d_png

    out_dir = os.path.join(ROOT, "docs", "devlog", "plates")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "sponza_r3d_firefly_cleanup.png")
    Image.fromarray(plate).save(out)
    print(f"[plate] wrote {out}")
    print(f"[plate] left half: R2d (DQLin baseline, firefly pathology)")
    print(f"[plate] right half: R3d (cell-pool first-writer-wins cleanup)")


if __name__ == "__main__":
    main()
