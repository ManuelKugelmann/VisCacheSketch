"""
make_r3d_firefly_heatmap.py - per-pixel error heatmap for the R2d vs R3d
Sponza comparison. Shows WHERE the firefly clusters concentrate
spatially, not just the aggregate brightness max.

For each scene in SCENES, generates 3-up grid:
  | R2d tonemap | R3d tonemap | err-diff heatmap (R2d_err - R3d_err) |

The third panel uses a magma colormap: bright pixels = R2d has much
more error than R3d (firefly hotspots where the cell-pool cleanup is
working). Dark pixels = no cleanup advantage.

Output: docs/devlog/plates/r3d_firefly_heatmap_{scene}.png

Pure-Python diagnostic; no shader paths touched.
"""
import os, sys, glob
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import OpenEXR, Imath
except ImportError:
    sys.exit("[heatmap] OpenEXR missing")
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("[heatmap] Pillow missing")

# Reuse existing OkLab utility from viscache_exr.
from viscache_exr import _oklab_distance_hdr


SCENES = ["Sponza", "BistroInterior", "BistroExterior"]
SPP = 16
BOUNCES = 4


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
    rgb = np.where(np.isfinite(rgb), np.maximum(rgb, 0.0), 0.0)
    tm = rgb / (1.0 + rgb)
    srgb = np.where(tm <= 0.0031308, 12.92 * tm, 1.055 * np.power(tm, 1.0 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255).astype(np.uint8)


def magma_colormap(t):
    """Approximate matplotlib magma colormap via piecewise lerp.
    t in [0,1] → 3-channel uint8 array of same leading shape."""
    # Magma stops (approximation, 5 anchors).
    stops = np.array([
        [0.001462, 0.000466, 0.013866],  # near-black
        [0.25, 0.06, 0.39],              # dark purple
        [0.65, 0.13, 0.45],              # red-purple
        [0.95, 0.45, 0.30],              # orange
        [0.99, 0.97, 0.74],              # cream
    ])
    t = np.clip(t, 0.0, 1.0)[..., None]
    n = stops.shape[0]
    idx = np.clip((t * (n - 1)).astype(np.int32), 0, n - 2)
    frac = t * (n - 1) - idx
    a = stops[idx[..., 0]]
    b = stops[idx[..., 0] + 1]
    rgb = a + (b - a) * frac
    return (np.clip(rgb, 0, 1) * 255.0).astype(np.uint8)


def find_capture(scene, variant_tag, spp=SPP, bounces=BOUNCES):
    glob_pat = os.path.join(
        ROOT, "runtime", "captures", "ladder", "RPT_ZOO", scene,
        f"s_x{spp}_*_restirpt_{variant_tag}_b{bounces}_hdr.exr",
    )
    hits = sorted(glob.glob(glob_pat))
    return hits[0] if hits else None


def find_gt(scene, bounces=BOUNCES):
    candidates = [
        os.path.join(ROOT, "runtime", "captures", "ladder", "00", scene,
                     f"s_x4096_512x512_vanilla_b{bounces}_hdr.exr"),
        os.path.join(ROOT, "runtime", "captures", "ladder", "00", scene,
                     f"s_x4096_512x512_vanilla_hdr.exr"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def label_image(img_arr, text, color=(255, 230, 80)):
    img = Image.fromarray(img_arr)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((9, 9), text, fill=(0, 0, 0), font=font)
    draw.text((8, 8), text, fill=color, font=font)
    return np.array(img)


def main():
    for scene in SCENES:
        r2d_path = find_capture(scene, "R2d")
        r3d_path = find_capture(scene, "R3d")
        gt_path = find_gt(scene)
        if not (r2d_path and r3d_path and gt_path):
            print(f"[heatmap] {scene}: skip (missing R2d={r2d_path}, R3d={r3d_path}, GT={gt_path})")
            continue
        r2d_err = _oklab_distance_hdr(r2d_path, gt_path)
        r3d_err = _oklab_distance_hdr(r3d_path, gt_path)
        if r2d_err is None or r3d_err is None:
            print(f"[heatmap] {scene}: OkLab compute failed")
            continue
        # err-diff: R2d - R3d. Positive = R3d wins (cleanup region); negative would mean R3d is worse (rare).
        diff = r2d_err - r3d_err
        diff_norm = np.clip(diff / max(diff.max(), 1e-6), 0.0, 1.0)
        heat = magma_colormap(diff_norm)

        r2d_tm = tone_map(load_exr_rgb(r2d_path))
        r3d_tm = tone_map(load_exr_rgb(r3d_path))

        r2d_tm = label_image(r2d_tm, f"{scene} R2d (DQLin)")
        r3d_tm = label_image(r3d_tm, f"{scene} R3d (cell-pool)")
        heat   = label_image(heat,
                             f"{scene} R2d_err - R3d_err  max={diff.max():.3f}  mean={diff.mean():.4f}",
                             color=(255, 255, 255))

        H = max(r2d_tm.shape[0], r3d_tm.shape[0], heat.shape[0])
        W = r2d_tm.shape[1] + r3d_tm.shape[1] + heat.shape[1]
        plate = np.zeros((H, W, 3), dtype=np.uint8)
        x = 0
        for img in (r2d_tm, r3d_tm, heat):
            plate[: img.shape[0], x : x + img.shape[1]] = img
            x += img.shape[1]

        out_dir = os.path.join(ROOT, "docs", "devlog", "plates")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"r3d_firefly_heatmap_{scene}.png")
        Image.fromarray(plate).save(out)
        print(f"[heatmap] {scene}: diff max={diff.max():.3f} mean={diff.mean():.4f} -> {out}")


if __name__ == "__main__":
    main()
