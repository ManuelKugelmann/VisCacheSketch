"""compare_restirpt_baseline.py — print summary stats across captures from
ReSTIRPT_Baseline_Test.py. For each (scene, bounces) cell, reports mean / std /
max luminance for vanilla and restirpt, plus a vanilla↔restirpt mean-abs-delta
in luminance to flag gross divergence (broken port symptom).

Run via runtime python:
  runtime/pythondist/python.exe scripts/compare_restirpt_baseline.py
"""
import os, sys, glob
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_exr import read_exr

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "runtime", "captures", "restirpt_baseline")
ROOT = os.path.abspath(ROOT)


def luma(rgb):
    """Rec.709 luminance for HDR float RGB[H,W,3]."""
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def load_color_exr(cell_dir, tag):
    """Load the frame-averaged radiance EXR for a captured cell. Both vanilla
    and (post-fix) restirpt write *.AccumulatePass.output.*.exr; pre-fix
    restirpt captures only have *.ReSTIRPTPass.color.*.exr (single-frame raw,
    not comparable but loaded as fallback).
    """
    candidates = (glob.glob(os.path.join(cell_dir, f"{tag}.AccumulatePass.output.*.exr")) +
                  glob.glob(os.path.join(cell_dir, f"{tag}.ReSTIRPTPass.color.*.exr")))
    if not candidates:
        return None
    chans = read_exr(candidates[0])
    rgb = chans.get("RGB", chans.get("RGBA"))
    if rgb is None:
        return None
    return rgb[:, :, :3]


def cell_dir_for(scene, tag):
    return os.path.join(ROOT, scene, tag)


def stats_row(scene, bounce, spp=1):
    """Return dict with luminance stats for vanilla & restirpt at (bounce, spp).
    Stats use finite values only; non-finite pixel count is reported separately
    so NaN/inf in ReSTIRPT outputs is visible.
    """
    out = {"scene": scene, "bounce": bounce, "spp": spp}
    bufs = {}
    for variant in ("vanilla", "restirpt"):
        tag = f"{variant}_b{bounce}_x{spp}"
        cdir = cell_dir_for(scene, tag)
        rgb = load_color_exr(cdir, tag)
        if rgb is None:
            out[variant] = None
            continue
        L = luma(rgb)
        finite = np.isfinite(L)
        n_nf = int((~finite).sum())
        Lf = L[finite]
        out[variant] = {
            "mean": float(Lf.mean()) if Lf.size else float("nan"),
            "std":  float(Lf.std())  if Lf.size else float("nan"),
            "max":  float(Lf.max())  if Lf.size else float("nan"),
            "p99":  float(np.percentile(Lf, 99)) if Lf.size else float("nan"),
            "non_finite": n_nf,
        }
        bufs[variant] = rgb
    if "vanilla" in bufs and "restirpt" in bufs and bufs["vanilla"].shape == bufs["restirpt"].shape:
        v = bufs["vanilla"]; r = bufs["restirpt"]
        finite = np.isfinite(v).all(axis=2) & np.isfinite(r).all(axis=2)
        d = np.abs(v - r)
        df = d[finite]
        out["mean_abs_diff"] = float(df.mean()) if df.size else float("nan")
        out["max_abs_diff"]  = float(df.max())  if df.size else float("nan")
        # relative diff in mean luminance — should be small if port is sane
        v_mean = max(1e-8, out["vanilla"]["mean"])
        out["restirpt_minus_vanilla_pct"] = 100.0 * (out["restirpt"]["mean"] - out["vanilla"]["mean"]) / v_mean
    return out


def main():
    if not os.path.isdir(ROOT):
        print(f"No captures at {ROOT}")
        return 1
    scenes = sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))
    if not scenes:
        print(f"No scene captures under {ROOT}")
        return 1

    rows = []
    for scene in scenes:
        scene_dir = os.path.join(ROOT, scene)
        # Discover (bounce, spp) cells from directory names
        seen = set()
        for cell in os.listdir(scene_dir):
            # cell format: <variant>_b<N>_x<S>
            try:
                _v, _b, _s = cell.split("_")
                if not (_b.startswith("b") and _s.startswith("x")):
                    continue
                bounce = int(_b[1:]); spp = int(_s[1:])
            except Exception:
                continue
            seen.add((bounce, spp))
        for bounce, spp in sorted(seen):
            rows.append(stats_row(scene, bounce, spp))

    # Print
    print(f"\n{'scene':<28s} {'b':>2s} {'spp':>3s}  "
          f"{'van L':>8s} {'rpt L':>8s} {'d%':>6s} "
          f"{'van max':>9s} {'rpt max':>9s} {'rpt nf':>7s}  "
          f"{'mean|d|':>8s} {'max|d|':>9s}")
    print("-" * 110)
    for r in rows:
        v = r.get("vanilla"); rp = r.get("restirpt")
        v_mean = f"{v['mean']:>8.4f}" if v else f"{'-':>8s}"
        rp_mean = f"{rp['mean']:>8.4f}" if rp else f"{'-':>8s}"
        v_max  = f"{v['max']:>9.2f}" if v else f"{'-':>9s}"
        rp_max = f"{rp['max']:>9.2f}" if rp else f"{'-':>9s}"
        rp_nf  = f"{rp['non_finite']:>7d}" if rp else f"{'-':>7s}"
        if v and rp:
            d_pct = f"{r.get('restirpt_minus_vanilla_pct', float('nan')):>+5.1f}%"
            mean_d = f"{r.get('mean_abs_diff', float('nan')):>8.4f}"
            max_d  = f"{r.get('max_abs_diff', float('nan')):>9.4f}"
        else:
            d_pct  = f"{'-':>6s}"
            mean_d = f"{'-':>8s}"
            max_d  = f"{'-':>9s}"
        print(f"{r['scene']:<28s} {r['bounce']:>2d} {r['spp']:>3d}  "
              f"{v_mean} {rp_mean} {d_pct} "
              f"{v_max} {rp_max} {rp_nf}  "
              f"{mean_d} {max_d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
