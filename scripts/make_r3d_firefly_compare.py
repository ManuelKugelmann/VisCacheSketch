"""
make_r3d_firefly_compare.py - multi-scene 2-up plate showing the
R3d-vs-R2d firefly-cleanup pattern across production scenes.

Stacks R2d/R3d capture pairs vertically for each scene where R3d's
DQLin-firefly-suppression side-effect is most visible:

  Sponza             | R2d max=2238, 27043 fireflies | R3d max=22.5, 0 fireflies
  BistroInterior     | R2d has inf pixels            | R3d clean
  BistroExterior     | R2d max=25968, 12575 fireflies| R3d clean

Output: docs/devlog/plates/r3d_firefly_compare_multiscene.png

Supersedes the single-scene make_sponza_r3d_compare.py (kept for
backwards reference; the multi-scene plate is the paper-ready one).
"""
import os, sys, glob
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import OpenEXR, Imath
except ImportError:
    sys.exit("[plate] OpenEXR missing")
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("[plate] Pillow missing")


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


def find_capture(scene, variant_tag, spp=SPP, bounces=BOUNCES):
    glob_pat = os.path.join(
        ROOT, "runtime", "captures", "ladder", "RPT_ZOO", scene,
        f"s_x{spp}_*_restirpt_{variant_tag}_b{bounces}_hdr.exr",
    )
    hits = sorted(glob.glob(glob_pat))
    return hits[0] if hits else None


def firefly_stats(rgb):
    finite = np.isfinite(rgb)
    inf_count = int((~finite).any(-1).sum())
    finite_rgb = np.where(finite, rgb, 0.0)
    max_brightness = float(finite_rgb.max())
    bright_count = int((finite_rgb > 100).any(-1).sum())
    return max_brightness, bright_count, inf_count


def label_image(img_arr, text, color=(255, 230, 80)):
    img = Image.fromarray(img_arr)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    # Black shadow + colored text for legibility.
    draw.text((9, 9), text, fill=(0, 0, 0), font=font)
    draw.text((8, 8), text, fill=color, font=font)
    return np.array(img)


def main():
    rows = []
    missing = []
    for scene in SCENES:
        r2d_path = find_capture(scene, "R2d")
        r3d_path = find_capture(scene, "R3d")
        if not r2d_path or not r3d_path:
            missing.append(scene)
            continue
        r2d_rgb = load_exr_rgb(r2d_path)
        r3d_rgb = load_exr_rgb(r3d_path)
        r2d_max, r2d_bright, r2d_inf = firefly_stats(r2d_rgb)
        r3d_max, r3d_bright, r3d_inf = firefly_stats(r3d_rgb)

        r2d_png = tone_map(r2d_rgb)
        r3d_png = tone_map(r3d_rgb)

        r2d_label = f"{scene} R2d   max={r2d_max:.0f}  >100px:{r2d_bright}  inf:{r2d_inf}"
        r3d_label = f"{scene} R3d   max={r3d_max:.0f}  >100px:{r3d_bright}  inf:{r3d_inf}"
        r2d_png = label_image(r2d_png, r2d_label)
        r3d_png = label_image(r3d_png, r3d_label)

        H = max(r2d_png.shape[0], r3d_png.shape[0])
        W = r2d_png.shape[1] + r3d_png.shape[1]
        row = np.zeros((H, W, 3), dtype=np.uint8)
        row[: r2d_png.shape[0], : r2d_png.shape[1]] = r2d_png
        row[: r3d_png.shape[0], r2d_png.shape[1] :] = r3d_png
        rows.append(row)
        print(f"[plate] {scene}: R2d max={r2d_max:.0f} fire={r2d_bright} | R3d max={r3d_max:.0f} fire={r3d_bright}")

    if not rows:
        sys.exit("[plate] no captures found in runtime/captures/ladder/RPT_ZOO/{Sponza,BistroInterior,BistroExterior}")
    if missing:
        print(f"[plate] WARN: missing captures for {missing}")

    # Stack rows vertically; all rows have same width if all scenes captured at 512.
    max_W = max(r.shape[1] for r in rows)
    padded = [r if r.shape[1] == max_W else np.pad(r, ((0,0), (0, max_W - r.shape[1]), (0,0))) for r in rows]
    plate = np.vstack(padded)

    out_dir = os.path.join(ROOT, "docs", "devlog", "plates")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "r3d_firefly_compare_multiscene.png")
    Image.fromarray(plate).save(out)
    print(f"[plate] wrote {out}  ({plate.shape[1]}x{plate.shape[0]})")


if __name__ == "__main__":
    main()
