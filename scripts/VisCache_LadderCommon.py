"""
VisCache_LadderCommon.py — Shared infrastructure for ladder test steps.

Provides:
- PRESET_MINIMAL + building blocks (RR_*, LEVELS_*, etc.)
- _make_variants(normal_active, quant, base): 5 addressing variants from preset + quant
- get_scenes(): resolve scene list from SCENES / SCENE_FILE env vars or defaults
- run_variants(): execute all variants × frame configs, capture + postprocess
- run_baseline(): render vanilla PathTracer baselines, skip if cached
- postprocess(): EXR → named PNG extraction with grid layout
- append_stats_csv(): upsert per-experiment row in per-step stats CSV
- plot_rays_overview(): scatter plot of rays traced % across scenes and variants
"""
import os, sys, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr import write_channel, load_diag_mask, find_exr, compute_render_noise, compute_render_error, compute_render_error_signed_hdr

# Track last-loaded scene to skip redundant m.loadScene() calls
_last_loaded_scene = None

def _load_scene_if_needed(m, scene_file, resX, resY):
    """Load scene after addGraph. Mogwai requires loadScene after each addGraph
    to rebind scene resources to the new render graph's passes."""
    m.loadScene(resolve_scene(scene_file))
    m.resizeFrameBuffer(resX, resY)

def resolve_scene(scene_file):
    """Resolve scene path: check PROJECT_ROOT/scenes/ and known data dirs (source mode), else pass through."""
    project_root = os.environ.get("PROJECT_ROOT", "")
    if project_root and not os.path.isabs(scene_file):
        basename = os.path.basename(scene_file)
        search_dirs = [
            os.path.join(project_root, "scenes"),
            os.path.join(project_root, "Source", "RenderPasses", "ReSTIRPTPass", "Data", "VeachAjar"),
        ]
        for d in search_dirs:
            candidate = os.path.join(d, basename)
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

# ===========================================================================
# Building blocks — combine to assemble step configs
# ===========================================================================

# --- Levels ----------------------------------------------------------------
LEVELS_SINGLE = {"numLevels": 1, "autoTuneCells": False}
LEVELS_MULTI  = {"numLevels": 8, "autoTuneCells": True}

# --- Quality ---------------------------------------------------------------
QUALITY_MINIMAL  = {"bootThreshold": 8,  "matureThreshold": 128, "varThreshold": 0.10}
QUALITY_DEFAULT  = {"bootThreshold": 16, "matureThreshold": 256, "varThreshold": 0.10}

# --- RR / pMin -------------------------------------------------------------
RR_OFF      = {"pMin": 1.0, "enableVisCacheAdaptivePMin": False, "fireflyBudget": 0.0}
RR_FIXED    = {"pMin": 0.05, "enableVisCacheAdaptivePMin": False, "fireflyBudget": 0.05}
RR_ADAPTIVE = {"pMin": 0.05, "enableVisCacheAdaptivePMin": True,  "fireflyBudget": 0.05}

# --- Features (toggle blocks) ---------------------------------------------
FEATURES_OFF = {
    "enableVisCacheJitterA": False,
    "enableVisCacheJitterB": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}

# --- Footprint trust scale (Ablation K) ----------------------------------
FOOTPRINT_OFF = {"enableVisCacheFootprintScale": False}
FOOTPRINT_ON  = {"enableVisCacheFootprintScale": True}

# --- Warmup write-only (Ablation L) --------------------------------------
# Warmup is now driven per-run by the frame_configs tuple:
# (warmupFirst, warmupRun, frames, [spp]). The run_variants call injects
# warmupSlotsFirst / warmupSlotsRun overrides, which the shader applies to
# determine per-pixel write-only status from the pixel's Bayer slot index.
# --- Subframe gate (Bayer N×N pixel interleaving to disperse cell-write order) ---
# 1 = full frame (default, no gate); 2 = 2×2 (4 subframes); 4 = 4×4 (16 subframes).
# Implemented via early-out in Falcor PathTracer (see Falcor/LOCAL_FIXES.md #14).
SUBFRAME_1x1  = {"subframeN": 1}
SUBFRAME_2x2  = {"subframeN": 2}
SUBFRAME_4x4  = {"subframeN": 4}
# --- Quantization cell sizes -----------------------------------------------
QUANT_SMALL   = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 5.0,  "distB": 0.24}
QUANT_MID     = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 8.0,  "distB": 0.48}
QUANT_DEFAULT = QUANT_SMALL

# Quantization sweep (step 03): 4 settings from fine to coarse, geometric in posA.
# Tag names embed in variant names via _make_variants quant_tag argument.
QUANT_SWEEP = {
    "qA": {"posA": 0.03, "normalA": 60.0, "posB": 0.09, "dirB":  5.0, "distB": 0.12},
    "qB": {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB":  8.0, "distB": 0.24},
    "qC": {"posA": 0.12, "normalA": 60.0, "posB": 0.36, "dirB": 15.0, "distB": 0.48},
    "qD": {"posA": 0.24, "normalA": 60.0, "posB": 0.72, "dirB": 30.0, "distB": 0.96},
}

# ===========================================================================
# Assembled presets — named combos of building blocks
# ===========================================================================

# The only preset needed so far — add more when ladder steps demand them
PRESET_MINIMAL = {**LEVELS_SINGLE, **QUALITY_MINIMAL, **RR_OFF, **FEATURES_OFF}

# ---------------------------------------------------------------------------
# Addressing variant groups
# ---------------------------------------------------------------------------
# Naming: A__B where __ separates endpoint A from B,
# _ separates dimensions within an endpoint. "1" suffix = collapsed/single bucket.
# pos_norm1__* = normal collapsed (off); pos_norm__* = normal active.
#
# Each group has the same 5 B-side configurations in the same order:
#   pos1, dir1_dist1, pos, dir_dist1, dir_dist

def _make_variants(normal_active, quant=None, base=None, quant_tag=None):
    """Generate 5 variants for one A-side config (norm1 or norm).
    B-side configs in order: pos1, dir1_dist1, pos, dir_dist1, dir_dist.
    quant: dict with posA, normalA, posB, dirB, distB keys.
    base: preset dict (default: PRESET_MINIMAL). Steps pick the preset closest
          to their needs and override the differences.
    quant_tag: optional string appended as __<tag> to the variant name (e.g. "qA").
    """
    q = quant or QUANT_DEFAULT
    b = base if base is not None else PRESET_MINIMAL
    prefix = "pos_norm" if normal_active else "pos_norm1"
    na = normal_active
    suffix = f"__{quant_tag}" if quant_tag else ""
    return [
        (f"{prefix}__pos1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": na,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "posBCoarse": 10000.0,
        }),
        (f"{prefix}__dir1_dist1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": 360.0,
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__pos{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": na,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "posBCoarse": q["posB"],
        }),
        (f"{prefix}__dir_dist1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": q["dirB"],
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__dir_dist{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": na,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": q["dirB"],
            "distBCoarse": q["distB"],
        }),
    ]

def make_norm_variants(quant=None, base=None, quant_tag=None):
    """The 3 non-collapsed norm-active variants: pos, dir_dist1, dir_dist.
    Working set from step 04 onward.
    """
    all_v = _make_variants(normal_active=True, quant=quant, base=base, quant_tag=quant_tag)
    # Strip by the dim pattern — match __posN or __dir1_dist1N where N is suffix or end.
    def is_collapsed(name):
        core = name.split("__")[1]  # e.g. "pos1" or "dir1_dist1"
        return core == "pos1" or core == "dir1_dist1"
    return [v for v in all_v if not is_collapsed(v[0])]


# ---------------------------------------------------------------------------
# Stats CSV
# ---------------------------------------------------------------------------
# key = f"{scene}_{prefix.rstrip('_')}" — encodes scene + frames + warmupSub + subframeN + res + variant
_CSV_FIELDS = ["key", "scene", "variant", "frames", "warmup_first", "warmup_run", "subframe_n",
               "rays_traced_pct", "coldmiss_pct", "timestamp"]

def _step_csv(step_name):
    return os.path.join("captures", "ladder", step_name, "stats.csv")

def append_stats_csv(step, scene, prefix, variant, frames, warmup_first, warmup_run, subframe_n,
                     rays_traced_pct, coldmiss_pct):
    """Upsert one row keyed by experiment identity (scene + config).
    key = f"{scene}_{prefix.rstrip('_')}" — encodes all run parameters.
    Re-run of the same experiment overwrites its row; different configs coexist.
    """
    import csv, datetime
    path = _step_csv(step)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    key = f"{scene}_{prefix.rstrip('_')}"
    new_row = {
        "key": key,
        "scene": scene, "variant": variant,
        "frames": str(frames),
        "warmup_first": str(warmup_first),
        "warmup_run":   str(warmup_run),
        "subframe_n":   str(subframe_n),
        "rays_traced_pct": f"{rays_traced_pct:.4f}",
        "coldmiss_pct":    f"{coldmiss_pct:.4f}",
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    rows = []
    replaced = False
    if os.path.exists(path):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                # Drop rows from old schemas (missing required fields).
                if any(k not in row for k in _CSV_FIELDS):
                    continue
                # Normalize to current field set.
                row = {k: row.get(k, "") for k in _CSV_FIELDS}
                if row.get("key") == key:
                    rows.append(new_row)
                    replaced = True
                else:
                    rows.append(row)
    if not replaced:
        rows.append(new_row)

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)

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
     ("r1c3_accum_error",      "GT-error Δ vs vanilla (black=denoised, purple=0, viridis=degraded)"),
     ("r1c9_accum_noise",      "render noise (vs GT)")],
    [("r2c1_frame_level",      "level"),
     ("r1c4_accum_maturity",   "maturity"),
     ("r1c5_accum_mean",       "mean"),
     ("r1c6_accum_variance",   "variance")],
    [("r1c7_accum_coldmiss",   "cold miss {coldmiss_pct:.1f}%"),
     ("r1c8_frame_qAhash",   "qA hash"),
     ("r2c8_frame_qBhash",   "qB hash"),
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
    Legend grouped: matching norm1/norm pairs adjacent, sorted by B-side complexity.
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
    # B-side → (marker, complexity rank 0–5)
    _B = {"pos1": ("D", 0), "dir1_dist1": ("s", 1), "pos": ("o", 2),
          "dir_dist1": ("^", 3), "dir_dist": ("v", 4)}
    # Hue family palettes: light→dark matches complexity rank
    _C_NORM1 = ["#aec7e8", "#1f77b4", "#17becf", "#0d6370", "#065040", "#083040"]  # blue/teal
    _C_NORM  = ["#ffbb78", "#ff7f0e", "#e05c1a", "#a03010", "#802010", "#601808"]  # orange/red

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
            return (99, 2, vname)
        a, b = vname.split("__", 1)
        fam = 0 if a == "pos_norm1" else (1 if a == "pos_norm" else 2)
        rank = _B.get(b, ("o", 99))[1]
        return (rank, fam, vname)

    variants_ordered = sorted(variants, key=_sort_key)

    # --- X positions: scenes + gap + "All" ---
    n_sc   = len(scenes)
    scene_x = {s: i for i, s in enumerate(scenes)}
    all_x   = n_sc + 0.5

    n_series = len(variants_ordered) * len(spps)
    spread   = 0.65
    offsets  = np.linspace(-spread / 2, spread / 2, n_series) if n_series > 1 else [0.0]

    fig, ax = plt.subplots(figsize=(max(7, (n_sc + 2) * 2.0), 5),
                           constrained_layout=True)

    series_idx = 0
    legend_handles = []
    for vname in variants_ordered:
        marker, color = _style(vname)
        for spp in spps:
            filled = (spp == spps[0])
            fc     = color if filled else "none"
            label  = f"{vname} x{spp}"

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

            if not pts:
                series_idx += 1
                continue
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

    ax.set_ylabel("Rays Traced %")
    ax.set_title(f"Step {step_name} — Rays Traced")
    ax.legend(handles=legend_handles, fontsize=6,
              loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0,
              ncol=1)
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", alpha=0.15)
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
    Row 1 (accum): render, raysTraced, GT-err Δ, maturity, mean, variance, coldmiss, qAHash, noise
    Row 2 (frame): level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, qBHash, probeSteps
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
    # Rays traced ratio from accumulated texture (masked to queried pixels)
    exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
    if exr:
        data = read_exr(exr).get("RGBA")
        if data is not None and data.shape[2] >= 4:
            rays = data[:, :, 0]
            if nd_accum is not None:
                mask = nd_accum > 0.5
                if mask.any():
                    stats["rays_traced_pct"] = float(rays[mask].mean() * 100)
            else:
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
    if exr: _wc(exr, 0, o("r1c8_frame_qAhash"), nodata=nd_frame)

    # --- Row 2: per-frame ---
    exr = find_exr(exrs, "FrameHashAHashBHashABRays")
    if exr:
        _wc(exr, 3, o("r2c2_frame_raystraced"))
        _wc(exr, 1, o("r2c8_frame_qBhash"),   nodata=nd_frame)
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

    # GT baselines for both error (signed Δ) and noise (absolute).
    gt_baselines = sorted(glob.glob(os.path.join(baseline_dir, "*_vanilla_hdr.exr")))
    gt_baselines = [b for b in gt_baselines if "_x1_" not in b]
    vanilla_xN_baselines = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_hdr.exr"))

    # Error: signed GT-error delta — err(viscache, GT) − err(vanilla_xN, GT).
    # Negative (purple) = VisCache denoised; positive (yellow) = VisCache degraded.
    if variant_hdr and vanilla_xN_baselines and gt_baselines:
        compute_render_error_signed_hdr(variant_hdr, vanilla_xN_baselines[0], gt_baselines[-1], o("r1c3_accum_error"))
        print(f"  [error] {os.path.basename(o('r1c3_accum_error'))}")
    elif variant_hdr and vanilla_xN_baselines:
        # No GT: fall back to absolute |viscache - vanilla_xN|
        from viscache_exr import compute_render_error_hdr
        compute_render_error_hdr(variant_hdr, vanilla_xN_baselines[0], o("r1c3_accum_error"))
        print(f"  [error] {os.path.basename(o('r1c3_accum_error'))} (no GT, falling back to |viscache − vanilla_xN|)")
    elif render_path:
        # Fallback: tonemapped PNG error
        error_baseline = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_r1c1_accum_render.png"))
        if error_baseline:
            compute_render_error(render_path, error_baseline[0], o("r1c3_accum_error"))
            print(f"  [error] {os.path.basename(o('r1c3_accum_error'))} (PNG fallback)")

    # Noise: |viscache_hdr - vanilla_gt_hdr| (ground truth, HDR)
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
                  maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None,
                  step_overrides=None, wipe_captures=True):
    """Run all variants × frame configs for a ladder step.
    mogwai_globals: pass globals() from the Mogwai script to access m, fc, etc.
    step_overrides: dict merged on top of each variant's overrides (e.g. pMin).
    wipe_captures: if False, don't wipe the capture dir (for chained calls).
    """
    if variants is None:
        raise ValueError("variants is required")
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_variants needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    res_tag = f"{resX}x{resY}"
    captureDir = f"captures/ladder/{step_name}/{scene_name}"

    # Wipe step×scene directory for clean output (unless chained).
    if wipe_captures and os.path.exists(captureDir):
        shutil.rmtree(captureDir, ignore_errors=True)
    os.makedirs(captureDir, exist_ok=True)

    all_stats = []
    for (variant_name, overrides) in variants:
        if step_overrides:
            overrides = {**overrides, **step_overrides}
        for fc_entry in frame_configs:
            # Frame config: (warmupFirst, warmupRun, frames, [spp=1])
            # warmupFirst: Bayer slots [0, warmupFirst) are write-only in frame 0
            # warmupRun:   Bayer slots [0, warmupRun) are write-only in every subsequent frame
            # frames:      logical frame count; scaled by N² so one logical frame = one full Bayer cycle
            warmupFirst, warmupRun, frames = fc_entry[0], fc_entry[1], fc_entry[2]
            spp = fc_entry[3] if len(fc_entry) > 3 else 1
            subN = overrides.get("subframeN", 1)
            render_frames = frames * subN * subN
            tag = f"s_{frames}_{warmupFirst}o{warmupRun}o{subN}x{subN}_{res_tag}"
            print(f"\n[{step_name}] ======== {variant_name} {tag} ({scene_name}) ========")

            # Inject warmup-write-only config for this run.
            # warmupSlotsFirst / warmupSlotsRun define the write-only Bayer ranges.
            run_overrides = {
                **overrides,
                "warmupSlotsFirst": warmupFirst,
                "warmupSlotsRun":   warmupRun,
            }

            saved = {}
            for k, v in run_overrides.items():
                if k in VISCACHE_DEFAULTS:
                    saved[k] = VISCACHE_DEFAULTS[k]
                VISCACHE_DEFAULTS[k] = v

            g = render_graph_PathTracer(viscache=True, maxBounces=maxBounces,
                                         samplesPerPixel=spp)

            for k, v in saved.items():
                VISCACHE_DEFAULTS[k] = v
            for k in run_overrides:
                if k not in saved and k in VISCACHE_DEFAULTS:
                    del VISCACHE_DEFAULTS[k]

            m.addGraph(g)
            _load_scene_if_needed(m, scene_file, resX, resY)

            os.makedirs(captureDir, exist_ok=True)
            fc.outputDir = captureDir
            fc.baseFilename = variant_name

            # Render `render_frames` = `frames * N²`. Write-only Bayer slots are
            # defined per-frame by warmupSlotsFirst (frame 0) and warmupSlotsRun
            # (frames 1..N-1). No separate warmup phase, no accum reset.
            for _ in range(render_frames):
                m.renderFrame()

            fc.capture()
            m.renderFrame()
            m.renderFrame()  # extra frame to ensure capture is fully flushed to disk

            print(f"[{step_name}] Captured ({tag})")
            pfx = f"{tag}_{variant_name}_"
            stats = postprocess(captureDir, pfx, variant_name, total_frames=render_frames, spp=spp, resX=resX, resY=resY)
            stitch_plate(captureDir, pfx, variant_name, stats=stats)

            # Collect stats for overview chart
            stats["variant"] = variant_name
            stats["scene"] = scene_name
            stats["spp"] = spp
            all_stats.append(stats)

            append_stats_csv(step_name, scene_name, pfx, variant_name,
                             frames, warmupFirst, warmupRun, subN,
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

    for fc_entry in frame_configs:
        # Tuple: (warmupFirst, warmupRun, frames, [spp=1]) — warmup fields ignored for vanilla.
        frames = fc_entry[2] if len(fc_entry) >= 3 else fc_entry[-1]
        captureDir = f"captures/ladder/{step_name}/{scene_name}"
        os.makedirs(captureDir, exist_ok=True)

        spp_list = sorted(set([1, gt_spp] + (extra_spp or [])))
        for spp in spp_list:
            tag = f"s_{frames}_x{spp}_{res_tag}"
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
            _load_scene_if_needed(m, scene_file, resX, resY)

            os.makedirs(captureDir, exist_ok=True)
            fc.outputDir = captureDir
            fc.baseFilename = f"vanilla_x{spp}"

            for _ in range(num_frames * frames):
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
