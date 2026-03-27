"""
VisCache_LadderCommon.py — Shared infrastructure for ladder test steps.

Provides:
- VARIANTS_POS_NORM1 / VARIANTS_POS_NORM / VARIANTS_ALL: addressing mode configurations
- BASE: shared base config (1 level, no jitter, all features off)
- run_variants(): execute all variants × frame configs, capture + postprocess
- postprocess(): EXR → named PNG extraction with grid layout
"""
import os, sys, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr import write_channel, load_diag_mask, find_exr, compute_render_noise, compute_render_error

def resolve_scene(scene_file):
    """Resolve scene path: check PROJECT_ROOT/scenes/ first (source mode), else pass through."""
    project_root = os.environ.get("PROJECT_ROOT", "")
    if project_root and not os.path.isabs(scene_file):
        candidate = os.path.join(project_root, "scenes", scene_file)
        if os.path.isfile(candidate):
            return candidate
    return scene_file

try:
    from falcor import *
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
kResX = 512
kResY = 512

# Default scene list for ladder tests.
ALL_SCENES = [
    "CornellBox_1AreaLight.pyscene",
    "CornellBox_1PointLight.pyscene",
    "CornellBox_3AreaLights.pyscene",
    "CornellBox_32PointLights.pyscene",
]

def get_scenes():
    """Resolve scene list from env vars.
    SCENES (comma-separated) > SCENE_FILE (single) > ALL_SCENES (default).
    """
    scenes_env = os.environ.get("SCENES", "")
    if scenes_env:
        return [s.strip() for s in scenes_env.split(",") if s.strip()]
    scene_file = os.environ.get("SCENE_FILE", "")
    if scene_file:
        return [scene_file]
    return ALL_SCENES

# Shared base: 1 level, no jitter, all features off, always trace
BASE = {
    "numLevels": 1,
    "cellACoarse": 0.06,
    "autoTuneCells": False,
    "bootThreshold": 4,
    "pMin": 1.0,
    "enableVisCacheJitterA": False,
    "enableVisCacheJitterB": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}

# ---------------------------------------------------------------------------
# Quantization presets
# ---------------------------------------------------------------------------
# Named size presets for B-side quantization bins.
# cellA is always from BASE (0.06). cellB/angular/dist/normal vary per preset.
QUANT_SMALL = {"cellB": 0.06, "angular": 5.0,  "dist": 0.24, "normal": 60.0}
QUANT_MID   = {"cellB": 0.12, "angular": 8.0,  "dist": 0.48, "normal": 60.0}
QUANT_LARGE = {"cellB": 0.24, "angular": 15.0, "dist": 1.0,  "normal": 90.0}

# ---------------------------------------------------------------------------
# Addressing variant groups
# ---------------------------------------------------------------------------
# Naming: A__B where __ separates endpoint A from B,
# _ separates dimensions within an endpoint. "1" suffix = collapsed/single bucket.
# pos_norm1__* = normal collapsed (off); pos_norm__* = normal active.
#
# Each group has the same 5 B-side configurations in the same order:
#   pos1, dir1_dist1, pos, dir_dist1, dir_dist

def _make_variants(normal_active, quant=None):
    """Generate 5 variants for one A-side config (norm1 or norm).
    quant: quantization preset dict with cellB, angular, dist, normal keys.
    """
    q = quant or QUANT_SMALL
    prefix = "pos_norm" if normal_active else "pos_norm1"
    na = normal_active
    return [
        (f"{prefix}__pos1", {
            **BASE,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": na,
            "normalBCoarse": q["normal"],
            "cellBCoarse": 10000.0,
        }),
        (f"{prefix}__dir1_dist1", {
            **BASE,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "normalBCoarse": q["normal"],
            "angularBCoarse": 360.0,
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__pos", {
            **BASE,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": na,
            "normalBCoarse": q["normal"],
            "cellBCoarse": q["cellB"],
        }),
        (f"{prefix}__dir_dist1", {
            **BASE,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "normalBCoarse": q["normal"],
            "angularBCoarse": q["angular"],
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__dir_dist", {
            **BASE,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "normalBCoarse": q["normal"],
            "angularBCoarse": q["angular"],
            "distBCoarse": q["dist"],
        }),
    ]

VARIANTS_POS_NORM1 = _make_variants(normal_active=False)
VARIANTS_POS_NORM  = _make_variants(normal_active=True)
VARIANTS_ALL       = VARIANTS_POS_NORM1 + VARIANTS_POS_NORM

# ---------------------------------------------------------------------------
# Stats CSV
# ---------------------------------------------------------------------------
_CSV_FIELDS = ["scene", "variant", "spp", "warmup", "averaging",
               "rays_traced_pct", "coldmiss_pct", "timestamp"]

def _step_csv(step_name):
    return os.path.join("captures", "ladder", step_name, "stats.csv")

def append_stats_csv(step, scene, variant, spp, warmup, averaging,
                     rays_traced_pct, coldmiss_pct):
    """Append one row to the per-step stats CSV (creates with header if absent)."""
    import csv, datetime
    path = _step_csv(step)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({
            "scene": scene, "variant": variant,
            "spp": spp, "warmup": warmup, "averaging": averaging,
            "rays_traced_pct": f"{rays_traced_pct:.4f}",
            "coldmiss_pct":    f"{coldmiss_pct:.4f}",
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        })

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _out(d, name, prefix=""):
    return os.path.join(d, f"{prefix}{name}.png")

def _wc(exr, ch, outpath, nodata=None, normalize_max=False):
    """Shorthand for write_channel with logging."""
    result = write_channel(exr, ch, outpath, nodata=nodata, normalize_max=normalize_max)
    if result:
        print(f"  [exr] {os.path.basename(result)}")
    return result

# (grid_name, label_template) pairs for plate tiles.
# {stat_key:.1f} placeholders are resolved from stats dict at stitch time.
PLATE_LAYOUT = [
    [("r1c1_accum_render",     "render"),
     ("r1c2_accum_raystraced", "rays traced {rays_traced_pct:.1f}%"),
     ("r1c3_accum_error",      "error vs baseline"),
     ("r1c9_accum_noise",      "render noise")],
    [("r2c1_frame_level",      "level"),
     ("r1c4_accum_maturity",   "maturity"),
     ("r1c5_accum_mean",       "mean"),
     ("r1c6_accum_variance",   "variance")],
    [("r1c7_accum_coldmiss",   "cold miss {coldmiss_pct:.1f}%"),
     ("r1c8_frame_posAhash",   "posA hash"),
     ("r2c8_frame_posBhash",   "posB hash"),
     ("r2c9_frame_probesteps", "probe steps")],
]

def stitch_plate(captureDir, prefix, variant_name, stats=None):
    """Stitch a 4×3 plate from extracted PNGs for devlog overview.
    Label templates in PLATE_LAYOUT can reference stats keys via {key:.1f} syntax.
    """
    from PIL import Image, ImageDraw, ImageFont
    cols, rows = 4, 3
    s = stats or {}

    cells = []
    labels = []
    for row in PLATE_LAYOUT:
        for name, tmpl in row:
            path = _out(captureDir, name, prefix)
            cells.append(Image.open(path) if os.path.exists(path) else None)
            labels.append(tmpl.format(**s))

    tile_w, tile_h = 512, 512
    for c in cells:
        if c is not None:
            tile_w, tile_h = c.size
            break

    font = ImageFont.load_default()
    try:
        font = ImageFont.truetype("arial.ttf", max(tile_w // 20, 12))
    except (IOError, OSError):
        pass

    title = prefix.rstrip("_")
    plate_w, plate_h = cols * tile_w, rows * tile_h
    plate = Image.new("RGB", (plate_w, plate_h), (0, 0, 0))
    draw = ImageDraw.Draw(plate)

    # Tiles
    for i, (cell, label) in enumerate(zip(cells, labels)):
        r, c = divmod(i, cols)
        x, y = c * tile_w, r * tile_h
        if cell is not None:
            plate.paste(cell.resize((tile_w, tile_h)), (x, y))
        tx, ty = x + 4, y + 2
        draw.text((tx + 1, ty + 1), label, fill=(0, 0, 0), font=font)
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)

    # Title: bottom right with shadow
    bbox = draw.textbbox((0, 0), title, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = plate_w - tw - 6, plate_h - th - 4
    draw.text((tx + 1, ty + 1), title, fill=(0, 0, 0), font=font)
    draw.text((tx, ty), title, fill=(200, 200, 200), font=font)

    scene_name = os.path.basename(captureDir)
    plate_dir = os.path.dirname(captureDir)
    out = _out(plate_dir, "plate", f"{scene_name}_{prefix}")
    plate.save(out)
    print(f"  [plate] {os.path.basename(out)}")
    return out

def plot_rays_overview(step_name):
    """Scatter: rays traced % — scene groups on x-axis, (variant×spp) series.

    Visual encoding axes:
      Hue family  : A-side (pos_norm1=blue/teal, pos_norm=orange/red)
      Lightness   : B-side complexity (pos1=light → dir_dist=dark within family)
      Marker shape: B-side type (D=pos1, s=dir1_dist1, o=pos, ^=dir_dist1, v=dir_dist)
      Filled/hollow: SPP (filled=lowest, hollow=higher)
    Rightmost "All" column = mean of per-scene means (equal scene weight).
    Legend grouped: norm1 family first, norm family second; SPP variants adjacent.
    """
    import csv, matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    csv_path = _step_csv(step_name)
    if not os.path.exists(csv_path):
        print(f"[overview] No stats CSV yet: {csv_path}")
        return None

    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["rays_traced_pct"] = float(row["rays_traced_pct"])
                row["spp"] = int(row["spp"])
            except (ValueError, KeyError):
                continue
            rows.append(row)

    if not rows:
        print(f"[overview] No data in {csv_path}")
        return None

    scenes   = sorted(set(r["scene"]   for r in rows))
    variants = sorted(set(r["variant"] for r in rows))
    spps     = sorted(set(r["spp"]     for r in rows))

    # --- Visual encoding ---
    # B-side → (marker, complexity rank 0–4)
    _B = {"pos1": ("D", 0), "dir1_dist1": ("s", 1), "pos": ("o", 2),
          "dir_dist1": ("^", 3), "dir_dist": ("v", 4)}
    # Hue family palettes: light→dark matches complexity rank
    _C_NORM1 = ["#aec7e8", "#1f77b4", "#17becf", "#0d6370", "#083040"]  # blue/teal
    _C_NORM  = ["#ffbb78", "#ff7f0e", "#e05c1a", "#a03010", "#601808"]  # orange/red

    def _style(vname):
        if "__" not in vname:
            return "o", "#888888"
        a, b = vname.split("__", 1)
        marker, rank = _B.get(b, ("o", 0))
        palette = _C_NORM1 if a == "pos_norm1" else (_C_NORM if a == "pos_norm" else None)
        color = palette[rank] if palette else plt.cm.tab10.colors[rank % 10]
        return marker, color

    # --- Legend order: norm1 family then norm family, each sorted by B-side rank,
    #     with SPP variants (filled/hollow) kept adjacent ---
    def _sort_key(vname):
        if "__" not in vname:
            return (2, 0, vname)
        a, b = vname.split("__", 1)
        fam = 0 if a == "pos_norm1" else (1 if a == "pos_norm" else 2)
        rank = _B.get(b, ("o", 99))[1]
        return (fam, rank, vname)

    variants_ordered = sorted(variants, key=_sort_key)

    # --- X positions: scenes + gap + "All" ---
    n_sc   = len(scenes)
    scene_x = {s: i for i, s in enumerate(scenes)}
    all_x   = n_sc + 0.5

    n_series = len(variants_ordered) * len(spps)
    spread   = 0.65
    offsets  = np.linspace(-spread / 2, spread / 2, n_series) if n_series > 1 else [0.0]

    fig, ax = plt.subplots(figsize=(max(7, (n_sc + 2) * 2.0), 5))

    series_idx = 0
    legend_handles = []
    for vname in variants_ordered:
        marker, color = _style(vname)
        for spp in spps:
            filled = (spp == spps[0])
            fc     = color if filled else "none"
            label  = vname if len(spps) == 1 else f"{vname} x{spp}"

            # Per-scene individual run dots
            pts = [(scene_x[r["scene"]] + offsets[series_idx], r["rays_traced_pct"])
                   for r in rows
                   if r["variant"] == vname and r["spp"] == spp
                   and r["rays_traced_pct"] >= 0]

            # "All" column: mean of per-scene means (equal scene weight)
            scene_means = []
            for s in scenes:
                sv = [r["rays_traced_pct"] for r in rows
                      if r["variant"] == vname and r["spp"] == spp
                      and r["scene"] == s and r["rays_traced_pct"] >= 0]
                if sv:
                    scene_means.append(float(np.mean(sv)))
            if scene_means:
                pts.append((all_x + offsets[series_idx], float(np.mean(scene_means))))

            if pts:
                xs, ys = zip(*pts)
                h = ax.scatter(xs, ys, label=label, marker=marker, color=color,
                               facecolors=fc, s=30, zorder=3)
                legend_handles.append(h)
            series_idx += 1

    # x-axis with separator
    ax.set_xticks(list(range(n_sc)) + [all_x])
    ax.set_xticklabels([s.replace("CornellBox_", "") for s in scenes] + ["All"],
                       rotation=20, ha="right", fontsize=9)
    ax.axvline(x=n_sc, color="#bbbbbb", linestyle="--", linewidth=0.8, zorder=1)

    spp_note = "filled=x" + str(spps[0]) + (f", hollow=x{spps[-1]}" if len(spps) > 1 else "")
    ax.set_ylabel("Rays Traced %")
    ax.set_title(f"Step {step_name} — Rays Traced  ({spp_note})")
    ax.legend(handles=legend_handles, fontsize=6, loc="best",
              ncol=max(1, len(variants_ordered) // 6))
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", alpha=0.15)
    plt.tight_layout()

    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"overview_rays_{step_name}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[overview] {out}")
    return out


def postprocess(captureDir, prefix, variant_name, total_frames=None, spp=1, resX=kResX, resY=kResY):
    """Extract named PNGs from EXR composites and rename Mogwai outputs.
    Filters by variant_name to avoid cross-variant contamination.

    total_frames: warmup + averaging frame count. Enables fractional nodata mask
                  (gradual darkening for pixels queried on fewer frames).
                  If None, nodata mask is binary.

    9-column grid (r<row>c<col> prefix):
    Row 1 (accum): render, raysTraced, error, maturity, mean, variance, coldmiss, posAHash, noise
    Row 2 (frame): level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, posBHash, probeSteps
    """
    vn = variant_name
    o = lambda name: _out(captureDir, name, prefix)
    exrs = glob.glob(os.path.join(captureDir, f"{vn}.*.exr"))

    # No-data masks: accum (fractional, from count+coldmissRate) vs frame (binary, from hashA+B==0)
    nd_accum = load_diag_mask(exrs, mode="nodata", total_frames=total_frames)
    nd_frame = load_diag_mask(exrs, mode="nodata_frame")

    # --- Compute global stats from EXR data ---
    stats = {"rays_traced_pct": -1.0, "coldmiss_pct": -1.0}
    from viscache_exr import read_exr
    import numpy as np
    # Rays traced ratio from accumulated texture
    exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
    if exr:
        data = read_exr(exr).get("RGBA")
        if data is not None and data.shape[2] >= 4:
            rays = data[:, :, 0]
            stats["rays_traced_pct"] = float(rays.mean() * 100)
    # Cold miss % from per-frame texture (matches what the plate shows)
    exr = find_exr(exrs, "FrameLevelProbesSamplesCold")
    if exr:
        data = read_exr(exr).get("RGBA")
        if data is not None and data.shape[2] >= 4:
            coldmiss = data[:, :, 3]  # A: 1=miss, 0=hit
            if nd_frame is not None:
                mask = nd_frame > 0.5  # only queried pixels
                if mask.any():
                    stats["coldmiss_pct"] = float(coldmiss[mask].mean() * 100)
            else:
                stats["coldmiss_pct"] = float(coldmiss.mean() * 100)

    # --- Row 1: accumulated ---
    exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
    if exr:
        _wc(exr, 0, o("r1c2_accum_raystraced"))
        _wc(exr, 2, o("r1c3_accum_error"),      nodata=nd_accum)
        _wc(exr, 3, o("r1c7_accum_coldmiss"),   nodata=nd_accum)
        _wc(exr, 1, o("r1c9_accum_noise"),      nodata=nd_accum)
    exr = find_exr(exrs, "AccumMeanVarMatCount")
    if exr:
        _wc(exr, 1, o("r1c4_accum_maturity"),   nodata=nd_accum)
        _wc(exr, 2, o("r1c5_accum_mean"),       nodata=nd_accum)
        _wc(exr, 0, o("r1c6_accum_variance"),   nodata=nd_accum)
    exr = find_exr(exrs, "FrameHashAHashBHashABRays")
    if exr: _wc(exr, 0, o("r1c8_frame_posAhash"), nodata=nd_frame)

    # --- Row 2: per-frame ---
    exr = find_exr(exrs, "FrameHashAHashBHashABRays")
    if exr:
        _wc(exr, 3, o("r2c2_frame_raystraced"))
        _wc(exr, 1, o("r2c8_frame_posBhash"),   nodata=nd_frame)
    exr = find_exr(exrs, "FrameLevelProbesSamplesCold")
    if exr:
        # Combine nodata + coldmiss for channels that should hide cold misses
        nd_nohit = nd_frame
        cm_data = read_exr(exr).get("RGBA") if exr else None
        if cm_data is not None and cm_data.shape[2] >= 4:
            import numpy as np
            coldmiss_binary = cm_data[:, :, 3]  # A channel: 1=cold miss, 0=hit
            nohit = np.clip(1.0 - coldmiss_binary, 0.0, 1.0).astype(np.float32)
            if nd_frame is not None:
                nd_nohit = nd_frame * nohit
            else:
                nd_nohit = nohit
        _wc(exr, 0, o("r2c1_frame_level"),       nodata=nd_nohit)
        _wc(exr, 2, o("r2c3_frame_samplecount"), nodata=nd_nohit)
        _wc(exr, 3, o("r2c7_frame_coldmiss"),    nodata=nd_frame)  # coldmiss itself uses nodata only
        _wc(exr, 1, o("r2c9_frame_probesteps"),  nodata=nd_nohit)
    exr = find_exr(exrs, "FrameMeanVarMatSamplesRaw")
    if exr:
        _wc(exr, 1, o("r2c4_frame_maturity"),   nodata=nd_frame)
        _wc(exr, 2, o("r2c5_frame_mean"),       nodata=nd_frame)
        _wc(exr, 0, o("r2c6_frame_variance"),   nodata=nd_frame)

    # --- Copy ToneMapper render to accum row ---
    render_path = None
    for src in glob.glob(os.path.join(captureDir, f"{vn}.ToneMapper.dst.*")):
        render_path = o("r1c1_accum_render")
        shutil.copy2(src, render_path)
        break

    # --- HDR baseline comparisons from step 00 ---
    scene_name = os.path.basename(captureDir)
    baseline_dir = os.path.join(os.path.dirname(captureDir), "..", "00", scene_name)

    # Find variant's HDR EXR (pre-tonemapper)
    variant_hdr = find_exr(glob.glob(os.path.join(captureDir, f"{vn}.*")), "AccumulatePass.output")

    # Error: |viscache_hdr - vanilla_xN_hdr| (same sample count, synced RNG, HDR)
    error_baselines = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_hdr.exr"))
    if variant_hdr and error_baselines:
        from viscache_exr import compute_render_error_hdr
        compute_render_error_hdr(variant_hdr, error_baselines[0], o("r1c3_accum_error"))
        print(f"  [error] {os.path.basename(o('r1c3_accum_error'))}")
    elif render_path:
        # Fallback: tonemapped PNG error
        error_baseline = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_r1c1_accum_render.png"))
        if error_baseline:
            compute_render_error(render_path, error_baseline[0], o("r1c3_accum_error"))
            print(f"  [error] {os.path.basename(o('r1c3_accum_error'))} (PNG fallback)")

    # Noise: |viscache_hdr - vanilla_gt_hdr| (ground truth, HDR)
    gt_baselines = sorted(glob.glob(os.path.join(baseline_dir, "*_vanilla_hdr.exr")))
    gt_baselines = [b for b in gt_baselines if "_x1_" not in b]
    if variant_hdr and gt_baselines:
        from viscache_exr import compute_render_error_hdr
        compute_render_error_hdr(variant_hdr, gt_baselines[-1], o("r1c9_accum_noise"))
        print(f"  [noise] {os.path.basename(o('r1c9_accum_noise'))}")
    elif render_path:
        # Fallback: tonemapped PNG noise
        gt_png = sorted(glob.glob(os.path.join(baseline_dir, "*_x[0-9]*_*_vanilla_r1c1_accum_render.png")))
        gt_png = [b for b in gt_png if "_x1_" not in b]
        if gt_png:
            compute_render_error(render_path, gt_png[-1], o("r1c9_accum_noise"))
            print(f"  [noise] {os.path.basename(o('r1c9_accum_noise'))} (PNG fallback)")

    # Cleanup raw EXRs and Mogwai outputs after channel extraction
    for f in exrs:
        try:
            os.remove(f)
        except (PermissionError, OSError):
            pass
    for f in glob.glob(os.path.join(captureDir, f"{vn}.*")):
        if not f.endswith(".png"):
            continue
        # Keep grid-named PNGs (with r1c/r2c prefix), delete raw Mogwai PNGs
        if os.path.basename(f).startswith(prefix):
            continue
        try:
            os.remove(f)
        except (PermissionError, OSError):
            pass

    return stats

def run_variants(step_name, frame_configs, scene_file, variants=None,
                  maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None):
    """Run all variants × frame configs for a ladder step.
    mogwai_globals: pass globals() from the Mogwai script to access m, fc, etc.
    """
    if variants is None:
        variants = VARIANTS_POS_NORM
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_variants needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    res_tag = f"{resX}x{resY}"
    captureDir = f"captures/ladder/{step_name}/{scene_name}"

    # Wipe step×scene directory for clean output
    if os.path.exists(captureDir):
        shutil.rmtree(captureDir, ignore_errors=True)
    os.makedirs(captureDir, exist_ok=True)

    all_stats = []
    for (variant_name, overrides) in variants:
        for fc_entry in frame_configs:
            warmup, averaging = fc_entry[0], fc_entry[1]
            spp = fc_entry[2] if len(fc_entry) > 2 else 1
            tag = f"s_{warmup}_{averaging}_x{spp}_{res_tag}"
            print(f"\n[{step_name}] ======== {variant_name} {tag} ({scene_name}) ========")

            saved = {}
            for k, v in overrides.items():
                if k in VISCACHE_DEFAULTS:
                    saved[k] = VISCACHE_DEFAULTS[k]
                VISCACHE_DEFAULTS[k] = v

            g = render_graph_PathTracer(viscache=True, maxBounces=maxBounces,
                                         samplesPerPixel=spp)

            for k, v in saved.items():
                VISCACHE_DEFAULTS[k] = v
            for k in overrides:
                if k not in saved and k in VISCACHE_DEFAULTS:
                    del VISCACHE_DEFAULTS[k]

            m.addGraph(g)
            m.loadScene(resolve_scene(scene_file))
            m.resizeFrameBuffer(resX, resY)

            os.makedirs(captureDir, exist_ok=True)
            fc.outputDir = captureDir
            fc.baseFilename = variant_name

            # Phase 1: warmup
            for _ in range(warmup):
                m.renderFrame()

            # Reset accum for clean averaging
            if warmup > 0:
                g.getPass("VisCache").set_properties({"resetAccum": True})

            # Phase 2: averaging
            for _ in range(averaging):
                m.renderFrame()

            fc.capture()
            m.renderFrame()
            m.renderFrame()  # extra frame to ensure capture is fully flushed to disk

            print(f"[{step_name}] Captured ({tag})")
            pfx = f"{tag}_{variant_name}_"
            # total_frames = averaging only (accum counters reset after warmup)
            stats = postprocess(captureDir, pfx, variant_name, total_frames=averaging, spp=spp, resX=resX, resY=resY)
            stitch_plate(captureDir, pfx, variant_name, stats=stats)

            # Collect stats for overview chart
            stats["variant"] = variant_name
            stats["scene"] = scene_name
            stats["spp"] = spp
            all_stats.append(stats)

            append_stats_csv(step_name, scene_name, variant_name, spp,
                             warmup, averaging,
                             stats["rays_traced_pct"], stats["coldmiss_pct"])

            m.removeGraph(g)

    print(f"\n[{step_name}] All done.")
    return all_stats


def run_baseline(step_name, frame_configs, scene_file,
                 maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None,
                 gt_spp=4096, extra_spp=None):
    """Run vanilla PathTracer (no VisCache) as baseline references.
    For each frame_config, renders baselines at 1 SPP, gt_spp, and any extra_spp values.
    For each frame_config, renders two baselines:
      1. 1spp vanilla (same sample count as VisCache — for error comparison)
      2. gt_spp vanilla (converged ground truth — for noise measurement)
         Same warmup+averaging frame count, but gt_spp samples per pixel per frame.
    Skips if cached from prior run.
    """
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_baseline needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    res_tag = f"{resX}x{resY}"

    for (warmup, averaging) in frame_configs:
        captureDir = f"captures/ladder/{step_name}/{scene_name}"
        os.makedirs(captureDir, exist_ok=True)

        spp_list = sorted(set([1, gt_spp] + (extra_spp or [])))
        for spp in spp_list:
            tag = f"s_{warmup}_{averaging}_x{spp}_{res_tag}"
            out_path = _out(captureDir, "r1c1_accum_render", f"{tag}_vanilla_")

            if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                print(f"\n[{step_name}] ======== vanilla_x{spp} {tag} ({scene_name}) — cached ========")
                continue

            print(f"\n[{step_name}] ======== vanilla_x{spp} {tag} ({scene_name}) ========")

            # Remap virtual SPP to Falcor params:
            # - Falcor caps samplesPerPixel at 16
            # - Higher counts: accumulate multiple frames via AccumulatePass
            # - Ground truth (spp > 16): disable jitter for edge-free comparison
            actual_spp = min(spp, 16)
            num_frames = max(1, spp // max(actual_spp, 1))
            use_jitter = (spp <= 16)  # no jitter for accumulated ground truth
            g = render_graph_PathTracer(viscache=False, maxBounces=maxBounces,
                                         samplesPerPixel=actual_spp, useJitter=use_jitter)
            m.addGraph(g)
            m.loadScene(resolve_scene(scene_file))
            m.resizeFrameBuffer(resX, resY)

            os.makedirs(captureDir, exist_ok=True)
            fc.outputDir = captureDir
            fc.baseFilename = f"vanilla_x{spp}"

            for _ in range(warmup):
                m.renderFrame()
            for _ in range(num_frames * averaging):
                m.renderFrame()

            fc.capture()
            m.renderFrame()
            m.renderFrame()  # extra frame to flush capture I/O

            print(f"[{step_name}] Captured ({tag})")

            # Copy capture files to grid-named outputs (wait for flush)
            import time
            time.sleep(0.5)

            # Tonemapped PNG
            matches = glob.glob(os.path.join(captureDir, f"vanilla_x{spp}.ToneMapper.dst.*"))
            if matches:
                src = matches[0]
                prev_sz = 0
                for _ in range(50):
                    sz = os.path.getsize(src)
                    if sz > 1024 and sz == prev_sz:
                        break
                    prev_sz = sz
                    time.sleep(0.1)
                shutil.copy2(src, out_path)
                print(f"[{step_name}] Copied {os.path.basename(out_path)} ({sz} bytes)")

            # Pre-tonemapper HDR EXR
            hdr_out = os.path.join(captureDir, f"{tag}_vanilla_hdr.exr")
            hdr_matches = glob.glob(os.path.join(captureDir, f"vanilla_x{spp}.AccumulatePass.output.*"))
            if hdr_matches:
                src = hdr_matches[0]
                prev_sz = 0
                for _ in range(50):
                    sz = os.path.getsize(src)
                    if sz > 1024 and sz == prev_sz:
                        break
                    prev_sz = sz
                    time.sleep(0.1)
                shutil.copy2(src, hdr_out)
                print(f"[{step_name}] Copied HDR {os.path.basename(hdr_out)} ({sz} bytes)")

            # Clean raw Mogwai outputs after copy
            for f in glob.glob(os.path.join(captureDir, f"vanilla_x{spp}.*")):
                try:
                    os.remove(f)
                except (PermissionError, OSError):
                    pass

            m.removeGraph(g)

    print(f"\n[{step_name}] All done.")
