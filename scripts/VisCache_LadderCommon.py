"""
VisCache_LadderCommon.py — Shared infrastructure for ladder test steps.

Provides:
- PRESET_MINIMAL + building blocks (RR_*, LEVELS_*, etc.)
- _make_variants(quant, base): 5 addressing variants from preset + quant (always norm-active)
- get_scenes(): resolve scene list from SCENES / SCENE_FILE env vars or defaults
- run_variants(): execute all variants × frame configs, capture + postprocess
- run_baseline(): render vanilla PathTracer baselines, skip if cached
- postprocess(): EXR → named PNG extraction with grid layout
- append_stats_csv(): upsert per-experiment row in per-step stats CSV
- plot_overviews(): emits 3 scatter plots per step — rays, GT-error Δ, noise
"""
import os, sys, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr import write_channel, load_diag_mask, find_exr, compute_render_noise, compute_render_noise_signed, compute_render_error, compute_render_error_signed_hdr, oklab_distance_hdr_cached

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

# --- Thresholds ------------------------------------------------------------
# Naming is neutral (low/mid/high refers to numeric boot/mature values, not
# implied quality). Tags match the th_low/th_mid/th_high scale used by the
# threshold-sweep steps (05/06/11/12).
THRESH_LOW  = {"bootThreshold":  4, "matureThreshold":  64, "varThreshold": 0.10}
THRESH_MID  = {"bootThreshold":  8, "matureThreshold": 128, "varThreshold": 0.10}
THRESH_HIGH = {"bootThreshold": 16, "matureThreshold": 256, "varThreshold": 0.10}

# --- RR / pMin -------------------------------------------------------------
RR_OFF      = {"pMin": 1.0, "enableVisCacheAdaptivePMin": False, "fireflyBudget": 0.0}
RR_FIXED    = {"pMin": 0.05, "enableVisCacheAdaptivePMin": False, "fireflyBudget": 0.05}
RR_ADAPTIVE = {"pMin": 0.05, "enableVisCacheAdaptivePMin": True,  "fireflyBudget": 0.05}

# --- Features (toggle blocks) ---------------------------------------------
FEATURES_OFF = {
    "jitterFilter": 0.0,
    "jitterCell": 0.0,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
    "enableVisCacheBootstrapBreak": False,
    "enableVisCacheParentPreinit": False,
}

# --- Footprint trust scale (Ablation K) ----------------------------------
# Single float knob (C++ member `footprintScale`). 0 = disabled (pure bootThreshold,
# equivalent to the old fpOff); 1 = log2(cellPixels) floor (old fpOn); values >1
# put more pressure on big cells. FOOTPRINT_OFF/ON here are legacy convenience
# aliases — prefer setting `footprintScale` directly in variant/step overrides.
FOOTPRINT_OFF = {"footprintScale": 0.0}
FOOTPRINT_ON  = {"footprintScale": 1.0}

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

# Quantization sweep (step 03): 3 settings from fine to coarse, ~2× posA per
# step except qcoarse which is bumped further out (3× qmid) to expose the
# "too coarse" regime. Tag names embed in variant names via _make_variants
# quant_tag argument.
QUANT_SWEEP = {
    "qfine":   {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB":  8.0, "distB": 0.24},
    "qmid":    {"posA": 0.12, "normalA": 60.0, "posB": 0.36, "dirB": 15.0, "distB": 0.48},
    "qcoarse": {"posA": 0.36, "normalA": 60.0, "posB": 1.08, "dirB": 45.0, "distB": 1.44},
}

# ===========================================================================
# Assembled presets — named combos of building blocks
# ===========================================================================

# The only preset needed so far — add more when ladder steps demand them
PRESET_MINIMAL = {**LEVELS_SINGLE, **THRESH_MID, **RR_OFF, **FEATURES_OFF}

# ---------------------------------------------------------------------------
# Addressing variant groups
# ---------------------------------------------------------------------------
# Naming: A__B where __ separates endpoint A from B,
# _ separates dimensions within an endpoint. "1" suffix = collapsed/single bucket.
# A-side is always pos_norm (normal-active) now; the pos_norm1 (normal-collapsed)
# family was retired — every step from 01 onward uses normal addressing on.
#
# 5 B-side configurations in order: pos1, dir1_dist1, pos, dir_dist1, dir_dist.

def _make_variants(quant=None, base=None, quant_tag=None):
    """Generate the 5 norm-active B-side variants: pos1, dir1_dist1, pos,
    dir_dist1, dir_dist. (norm-collapsed variants are retired — pos_norm
    with normalAddr on is the default for everything from step 01+.)
    quant: dict with posA, normalA, posB, dirB, distB keys.
    base: preset dict (default: PRESET_MINIMAL). Steps pick the preset closest
          to their needs and override the differences.
    quant_tag: optional string appended as __<tag> to the variant name (e.g. "qA").
    """
    q = quant or QUANT_DEFAULT
    b = base if base is not None else PRESET_MINIMAL
    prefix = "pos_norm"
    suffix = f"__{quant_tag}" if quant_tag else ""
    return [
        (f"{prefix}__pos1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": True,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "posBCoarse": 10000.0,
        }),
        (f"{prefix}__dir1_dist1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": True,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": 360.0,
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__pos{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": True,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "posBCoarse": q["posB"],
        }),
        (f"{prefix}__dir_dist1{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": True,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": q["dirB"],
            "distBCoarse": 1000.0,
        }),
        (f"{prefix}__dir_dist{suffix}", {
            **b,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": True,
            "posACoarse": q["posA"],
            "normalACoarse": q["normalA"],
            "dirBCoarse": q["dirB"],
            "distBCoarse": q["distB"],
        }),
    ]

def make_norm_variants(quant=None, base=None, quant_tag=None):
    """The 3 non-collapsed B-side variants: pos, dir_dist1, dir_dist.
    Working set from step 04 onward (step 05+ drops dir_dist1 further).
    """
    all_v = _make_variants(quant=quant, base=base, quant_tag=quant_tag)
    def is_collapsed(name):
        core = name.split("__")[1]
        return core == "pos1" or core == "dir1_dist1"
    return [v for v in all_v if not is_collapsed(v[0])]


# ---------------------------------------------------------------------------
# Stats CSV
# ---------------------------------------------------------------------------
# key = f"{scene}_{prefix.rstrip('_')}" — encodes scene + frames + warmupSub + subframeN + res + variant
_CSV_FIELDS = ["key", "scene", "variant", "spp", "frames", "warmup_first", "warmup_run", "subframe_n",
               "rays_traced_pct", "coldmiss_pct",
               "error_delta_pct", "error_delta_min_pct", "error_delta_max_pct",
               "error_delta_blob_pct",
               "noise_delta_pct", "noise_delta_min_pct", "noise_delta_max_pct",
               "noise_delta_blob_pct",
               "timestamp"]

def _step_csv(step_name):
    return os.path.join("captures", "ladder", step_name, "stats.csv")

def append_stats_csv(step, scene, prefix, variant, spp, frames, warmup_first, warmup_run, subframe_n,
                     rays_traced_pct, coldmiss_pct,
                     error_delta_pct=None, error_delta_min_pct=None, error_delta_max_pct=None,
                     error_delta_blob_pct=None,
                     noise_delta_pct=None, noise_delta_min_pct=None, noise_delta_max_pct=None,
                     noise_delta_blob_pct=None):
    """Upsert one row keyed by experiment identity (scene + config).
    key = f"{scene}_{prefix.rstrip('_')}" — encodes all run parameters.
    Re-run of the same experiment overwrites its row; different configs coexist.

    error_delta_pct: signed mean-% (err_vis_gt − err_van_gt) / err_van_gt × 100 (OkLab, vs GT).
    error_delta_{min,max}_pct: per-pixel min/max of the same signed delta, same normalization.
    error_delta_blob_pct: signed worst-blob value (Gaussian-blurred delta, sign preserved).
    noise_delta_pct: signed mean-% (noise_vis − noise_van) / noise_van × 100 (bilateral screen noise).
    noise_delta_{min,max}_pct: per-pixel min/max of the same signed delta.
    noise_delta_blob_pct: signed worst-blob value of the same bilateral-noise delta.
    """
    import csv, datetime
    path = _step_csv(step)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    key = f"{scene}_{prefix.rstrip('_')}"
    new_row = {
        "key": key,
        "scene": scene, "variant": variant,
        "spp": str(spp),
        "frames": str(frames),
        "warmup_first": str(warmup_first),
        "warmup_run":   str(warmup_run),
        "subframe_n":   str(subframe_n),
        "rays_traced_pct": f"{rays_traced_pct:.4f}",
        "coldmiss_pct":    f"{coldmiss_pct:.4f}",
        "error_delta_pct":      f"{error_delta_pct:.4f}"      if error_delta_pct      is not None else "",
        "error_delta_min_pct":  f"{error_delta_min_pct:.4f}"  if error_delta_min_pct  is not None else "",
        "error_delta_max_pct":  f"{error_delta_max_pct:.4f}"  if error_delta_max_pct  is not None else "",
        "error_delta_blob_pct": f"{error_delta_blob_pct:.4f}" if error_delta_blob_pct is not None else "",
        "noise_delta_pct":      f"{noise_delta_pct:.4f}"      if noise_delta_pct      is not None else "",
        "noise_delta_min_pct":  f"{noise_delta_min_pct:.4f}"  if noise_delta_min_pct  is not None else "",
        "noise_delta_max_pct":  f"{noise_delta_max_pct:.4f}"  if noise_delta_max_pct  is not None else "",
        "noise_delta_blob_pct": f"{noise_delta_blob_pct:.4f}" if noise_delta_blob_pct is not None else "",
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


# Baseline (step 00) CSV — absolute error/noise per (scene, spp). Distinct
# schema from the variant CSV: no deltas, no rays/coldmiss, no warmup/subframe.
_CSV_BASELINE_FIELDS = ["key", "scene", "spp",
                        "mean_err_pct", "max_err_pct", "mean_noise_pct",
                        "timestamp"]

def append_baseline_csv(step, scene, spp, mean_err_pct, max_err_pct, mean_noise_pct):
    """Upsert one baseline row keyed by (scene, spp)."""
    import csv, datetime
    path = _step_csv(step)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    key = f"{scene}_x{spp}"
    new_row = {
        "key": key, "scene": scene, "spp": str(spp),
        "mean_err_pct":   f"{mean_err_pct:.4f}"   if mean_err_pct   is not None else "",
        "max_err_pct":    f"{max_err_pct:.4f}"    if max_err_pct    is not None else "",
        "mean_noise_pct": f"{mean_noise_pct:.4f}" if mean_noise_pct is not None else "",
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    rows = []
    replaced = False
    if os.path.exists(path):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if any(k not in row for k in _CSV_BASELINE_FIELDS):
                    continue
                row = {k: row.get(k, "") for k in _CSV_BASELINE_FIELDS}
                if row.get("key") == key:
                    rows.append(new_row)
                    replaced = True
                else:
                    rows.append(row)
    if not replaced:
        rows.append(new_row)

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_BASELINE_FIELDS)
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
     ("r1c3_accum_error",      "error Δ μ{error_delta_pct:+.1f}% blob{error_delta_blob_pct:+.1f}%"),
     ("r1c9_accum_noise",      "noise Δ μ{noise_delta_pct:+.1f}% blob{noise_delta_blob_pct:+.1f}%")],
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

    # None-safe: replace None with NaN so numeric format specifiers don't crash.
    s_fmt = {k: (float("nan") if v is None else v) for k, v in s.items()}

    cells = []
    labels = []
    for row in PLATE_LAYOUT:
        for name, tmpl in row:
            path = _out(captureDir, name, prefix)
            cells.append(Image.open(path) if os.path.exists(path) else None)
            labels.append(tmpl.format(**s_fmt))

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

def stitch_baseline_plate(captureDir, xN_tag, out_path, err_stats=None, noise_stats=None):
    """1×3 plate for a vanilla baseline: render | error vs GT | noise.
    Mirrors the informative cells of row 1 of the variant plate layout. The rays
    column is omitted because vanilla always traces 100%.

    err_stats / noise_stats: dicts returned by compute_render_error_hdr /
    compute_render_noise — used to decorate the labels with the same
    `μ…% max…%` format variant plates use. None → fall back to plain text.
    """
    def _err_label():
        if not err_stats:
            return "error"
        return f"error μ{err_stats['mean_err_pct']:.1f}% max{err_stats['max_err_pct']:.1f}%"

    def _noise_label():
        if not noise_stats:
            return "noise"
        return f"noise μ{noise_stats['mean_noise_pct']:.1f}%"
    from PIL import Image, ImageDraw, ImageFont
    import os

    render_path = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c1_accum_render.png")
    err_path    = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c3_accum_error.png")
    noise_path  = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c9_accum_noise.png")

    cells = [
        Image.open(render_path) if os.path.exists(render_path) else None,
        Image.open(err_path) if os.path.exists(err_path) else None,
        Image.open(noise_path) if os.path.exists(noise_path) else None,
    ]
    labels = ["render", _err_label(), _noise_label()]

    # Find tile size from any populated cell.
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

    plate_w, plate_h = 3 * tile_w, tile_h
    plate = Image.new("RGB", (plate_w, plate_h), (0, 0, 0))
    draw = ImageDraw.Draw(plate)

    for i, (cell, label) in enumerate(zip(cells, labels)):
        x, y = i * tile_w, 0
        if cell is not None:
            plate.paste(cell.resize((tile_w, tile_h)), (x, y))
        tx, ty = x + 4, y + 2
        draw.text((tx + 1, ty + 1), label, fill=(0, 0, 0), font=font)
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)

    title = f"{xN_tag}_vanilla"
    bbox = draw.textbbox((0, 0), title, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = plate_w - tw - 6, plate_h - th - 4
    draw.text((tx + 1, ty + 1), title, fill=(0, 0, 0), font=font)
    draw.text((tx, ty), title, fill=(200, 200, 200), font=font)

    plate.save(out_path)
    print(f"  [plate] {os.path.basename(out_path)}")
    return out_path


# Shared y-axis limits — consistent across all ladder steps so plots can be
# compared directly (and differences are not masked by per-step autoscaling).
# Spans cover the observed-ranges headroom (~-1.5 → 150% error, ~75% noise).
RAYS_YLIM         = (0, 105)
ERROR_DELTA_YLIM  = (-10, 200)
NOISE_DELTA_YLIM  = (-10, 100)
# Baseline (step 00): absolute error/noise (unsigned).
ERROR_ABS_YLIM    = (0, 200)
NOISE_ABS_YLIM    = (0, 100)


# One-line theme per ladder step — what that step's run is evaluating.
# Shows up in the plot titles so viewers know what the scatter is comparing.
# Title format: "<mission>: <what's swept / varied> (<ambient state: level, RR,
# feature flags, variant subset>)". Mission is a short noun phrase naming what
# the step evaluates; parens carry the static-for-this-step context so any
# single plot can be read standalone.
_STEP_TITLES = {
    "00": "Vanilla baselines: no VisCache",
    "01": "Cold start issues: subframe warmup sweep (single level)",
    "02": "Addressing sweep: 5 B-side variants (single level)",
    "03": "Quantization sweep: 4 quant presets (single level)",
    "04": "Sample count sweep: x1 / x4 / x8 / x16 SPP (single level)",
    "05": "Threshold sweep: footprint off (single level)",
    "06": "Threshold × footprint sweep: 3×3 grid (single level)",
    "07": "Footprint sweep at th_mid (single level)",
    "08": "Head-to-head: 2 quant × 2 threshold × 3 footprint (single level)",
    "09": "Jitter head-to-head (single level)",
    "10": "Cascade depth sweep: numLevels 4 / 6 / 8 / 16 (multi-level, footprint on)",
    "11": "Threshold × footprint sweep: 3×3 grid (multi-level)",
    "14": "Head-to-head: 2 quant × 2 threshold × 3 footprint (multi-level)",
}

def _step_title(step_name):
    return _STEP_TITLES.get(step_name, "")


def _plot_metric(rows, step_name, metric_key, ylabel, title_suffix, out_suffix,
                 ylim=None, zero_line=False, include_neg=False,
                 whisker_blob_key=None,
                 symlog_linthresh=None,
                 ax=None, save=True, prev_winner=None):
    """Scatter: one metric — scene groups on x-axis, (variant×spp) series.

    Visual encoding axes:
      Hue family  : step's main-topic sweep tag (quant / quality) when present,
                    else orange/red ramp on B-side complexity rank
      Lightness   : B-side complexity (pos1=light → dir_dist=dark within family)
      Marker shape: B-side type (D=pos1, s=dir1_dist1, o=pos, ^=dir_dist1, v=dir_dist)
      Filled/hollow: SPP (filled=lowest, hollow=higher)
    Rightmost "All" column = mean of per-scene means (equal scene weight).

    metric_key: row key to plot. Rows where row[metric_key] is None are skipped.
    include_neg: if False, also skip rows where value < 0 (sentinel for missing data
                 in non-signed metrics). Leave True for signed metrics (error delta).
    whisker_blob_key: optional row key holding the signed worst-correlated-blob value
                 (Gaussian-blurred peak, sign preserved). Drawn as a single-sided
                 vertical line from the mean point to the blob value, with a tick
                 at the whisker end. "All" column whisker spans to the worst-scene
                 blob value (max |value| across scenes).
    ax/save: when ax is provided, plot onto that axis and skip file I/O — used by
             the combined multi-panel plot.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba
    import numpy as np

    # Scenes ordered by rising difficulty (few / simple lights → many / complex).
    # Unknown scenes sort alphabetically after the known ones.
    _SCENE_ORDER = [
        "CornellBox_1PointLight",
        "CornellBox_1AreaLight",
        "CornellBox_3AreaLights",
        "CornellBox_32PointLights",
    ]
    def _scene_key(s):
        return (_SCENE_ORDER.index(s), s) if s in _SCENE_ORDER else (len(_SCENE_ORDER), s)
    scenes   = sorted({r["scene"] for r in rows}, key=_scene_key)
    variants = sorted(set(r["variant"] for r in rows))
    spps     = sorted(set(r["spp"]     for r in rows if r["spp"] is not None))
    if not spps:
        spps = [1]  # fallback for CSVs without spp

    # Shape family convention: one glyph per addressing family, with fill
    # distinguishing the collapsed sibling (ends in "1"). Addressing variants
    # get pruned quickly past step 04, so fill is safely reused for footprint
    # state in later steps — there's never both a collapsed-sibling pair AND
    # an fpOn/fpOff split on the same shape in the same run.
    _B = {"pos1":       ("o", 0),  # circle (collapsed → hollow via fill)
          "pos":        ("o", 2),  # circle (filled)
          "dir1_dist1": ("D", 1),  # diamond (both collapsed → hollow; visual
                                   # blend between circle-family and triangle-family)
          "dir_dist1":  ("v", 3),  # triangle-down (dist collapsed → hollow)
          "dir_dist":   ("v", 4)}  # triangle-down (filled)
    # Single A-side family now (pos_norm, always norm-active) — orange/red
    # ramps from light to dark with B-side complexity rank.
    _C_NORM = ["#ffbb78", "#ff7f0e", "#e05c1a", "#a03010", "#802010", "#601808"]

    # Visual axes:
    #   hue family    → step's main-topic sweep tag (quant / quality) when present
    #   marker shape  → B-side core (consistent across all steps)
    #   marker fill   → footprint (filled=fpOff / no-tag baseline;
    #                   hollow=fpOn under test)
    #   marker size   → SPP (small → large as SPP grows)
    #   alpha         → quant / sweep tag ordering

    def _parse(vname):
        """Split variant name into (A-side, B-core, latest_tag).
        The latest tag is parts[-1] — step N inherits the step-(N-1) winner
        as parts[2] and layers its own sweep tag as parts[3+]. Using parts[-1]
        picks up the step's own topic axis.
        Examples:
          pos_norm__dir_dist1                            → ("pos_norm", "dir_dist1", None)
          pos_norm__dir_dist1__qA                        → ("pos_norm", "dir_dist1", "qA")
          pos_norm__pos__qD__th_mid_fpOff                → ("pos_norm", "pos", "th_mid_fpOff")
          pos_norm__pos__qD__fpOff_th_mid                → ("pos_norm", "pos", "fpOff_th_mid")
        """
        if "__" not in vname:
            return None, None, None
        parts = vname.split("__")
        a = parts[0]
        b = parts[1] if len(parts) > 1 else None
        tag = parts[-1] if len(parts) > 2 else None
        return a, b, tag

    def _is_fp_token(t):
        """True for fpOn / fpOff / fp<N> / fpS<N> (legacy) footprint-scale tags."""
        if t in ("fpOn", "fpOff"):
            return True
        if t.startswith("fpS") and len(t) > 3 and t[3:].isdigit():
            return True
        if t.startswith("fp") and len(t) > 2 and t[2:].isdigit():
            return True
        return False

    def _fp_scale_val(tag):
        """Extract footprint scale value from any fp* token in the tag.
        fpOff / fp0 → 0.0; fpOn / fp1 → 1.0; fp05 → 0.5; fp2 → 2.0.
        fpS<N> legacy form also supported. Returns None if no fp token."""
        if tag is None:
            return None
        for t in tag.split("_"):
            if t == "fpOff": return 0.0
            if t == "fpOn":  return 1.0
            if t.startswith("fpS") and len(t) > 3 and t[3:].isdigit():
                return _scale_val(t[3:])
            if t.startswith("fp") and len(t) > 2 and t[2:].isdigit():
                return _scale_val(t[2:])
        return None

    def _hue_key(tag):
        """Strip fp* tokens (scale encoded in fill alpha, not hue) and return
        the main topic. If nothing but fp tokens remain (pure scale sweep,
        e.g. step 07), return None so hue falls back to the B-core color
        (uniform across the sweep) and the fp scale is communicated solely
        by fill transparency — monotonic, single-hue ramp in the legend.
          qA                → qA
          th_mid_fpOff      → th_mid
          th_low_fp05       → th_low
          fp1               → None    (scale-only sweep → alpha encodes it)
        """
        if tag is None:
            return None
        toks   = tag.split("_")
        non_fp = [t for t in toks if not _is_fp_token(t)]
        if non_fp:
            return "_".join(non_fp)
        return None

    # Global ordering of hue keys (main-topic tag values) — drives the step's
    # dominant color axis. When present, hue encodes this rather than A-side.
    # Semantic ordering overrides alpha sort for known ramps: low → mid → high
    # for threshold tags (th_low/th_mid/th_high) keeps the legend reading in
    # the natural "cool → warm" progression. fpS<N> tokens encode footprint
    # scale with "05" meaning 0.5 (so fpS05 sorts before fpS1 numerically).
    _SEMANTIC_ORDER = {"low": 0, "mid": 1, "high": 2}
    def _scale_val(s):
        # fpS suffix → float. "0"→0, "05"→0.5, "1"→1, "2"→2, "4"→4, "10"→10.
        if s.startswith("0") and len(s) > 1:
            try: return float("0." + s[1:])
            except ValueError: return 99.0
        try: return float(s)
        except ValueError: return 99.0
    def _tag_sort_key(k):
        toks = k.split("_")
        th_rank = 99
        for i in range(len(toks) - 1):
            if toks[i] == "th" and toks[i+1] in _SEMANTIC_ORDER:
                th_rank = _SEMANTIC_ORDER[toks[i+1]]
                break
        scale_rank = -1.0  # no scale token → sorts before any fp-tagged variant
        sv = _fp_scale_val(k)
        if sv is not None:
            scale_rank = sv
        # Fallback to suffix semantic for simple tags (th_low etc).
        suffix = toks[-1]
        suffix_rank = _SEMANTIC_ORDER.get(suffix, 99)
        return (th_rank, scale_rank, suffix_rank, k)
    _all_tags    = sorted({_parse(v)[2] for v in variants if _parse(v)[2] is not None},
                          key=_tag_sort_key)

    def _alpha(vname):
        """With hue now encoding the main-topic tag, the alpha gradient is
        retired — every point is fully opaque."""
        return 1.0

    # Palette for the step's main-topic hue axis (when _hue_keys is non-empty).
    _TAG_PALETTE = plt.cm.tab10.colors

    # Quant markers (step 03 sweep) and threshold markers (step 08/14 head-to-head).
    _QUANT_MARKERS  = {"qfine": "D", "qmid": "o", "qcoarse": "s"}
    _THRESH_MARKERS = {"th_low": "v", "th_mid": "o", "th_high": "^"}

    def _quant_of(vname):
        for p in vname.split("__"):
            if p in _QUANT_MARKERS: return p
            for t in p.split("_"):
                if t in _QUANT_MARKERS: return t
        return None

    def _thresh_of(vname):
        for m in _THRESH_MARKERS:
            if m in vname: return m
        return None

    # Detect head-to-head steps: when BOTH quant and threshold axes vary across
    # the variant set, swap the encoding — hue = quant, marker = threshold —
    # so each axis has its own visual channel instead of both sharing marker.
    _quants_in_set  = {_quant_of(v)  for v in variants} - {None}
    _thresh_in_set  = {_thresh_of(v) for v in variants} - {None}
    _swap_encoding  = len(_quants_in_set) > 1 and len(_thresh_in_set) > 1

    def _hue_override(vname):
        """Override the hue key when quant-threshold swap is active."""
        if _swap_encoding:
            return _quant_of(vname)
        return _hue_key(_parse(vname)[2])

    _hue_keys = sorted({_hue_override(v) for v in variants
                        if _hue_override(v) is not None},
                       key=_tag_sort_key)

    def _style(vname):
        a, b_core, tag = _parse(vname)
        if a is None:
            return "o", "#888888"
        # Default: marker = B-core (addressing variant — consistent with the
        # step 02 sweep and propagates into downstream steps where B-core stays
        # fixed at the step-04 winner). Only the head-to-head (2 quant × 2 thresh)
        # case overrides marker to encode threshold, since B-core is single there.
        marker, rank = _B.get(b_core, ("o", 0))
        if _swap_encoding:
            th = _thresh_of(vname)
            if th is not None:
                marker = _THRESH_MARKERS[th]
        hue = _hue_override(vname)
        if hue is not None and hue in _hue_keys:
            # Hue = the step's main-topic tag (quant / quality / sweep id).
            color = _TAG_PALETTE[_hue_keys.index(hue) % len(_TAG_PALETTE)]
        else:
            # Fallback: B-side complexity rank picks a shade in the pos_norm palette.
            color = _C_NORM[rank] if rank < len(_C_NORM) else _TAG_PALETTE[rank % len(_TAG_PALETTE)]
        return marker, color

    def _fp_alpha(vname):
        """Face-fill alpha for scatter markers, encoding footprint scale:
          - fpOff / fp0   → 0.0 (hollow)
          - fp05          → 0.5 (half-filled)
          - fpOn / fp1    → 1.0 (solid)
          - fp2, fp4, …   → 1.0 (saturate; past 1.0 the visual just reads "on")
          - No fp token, B-core ends in '1' (collapsed sibling) → 0.0
          - No fp token otherwise → 1.0
        Lets steps with a fp-scale axis (e.g. step 06) encode the ramp via
        fill transparency while hue stays free for the threshold axis.
        """
        _, b_core, tag = _parse(vname)
        scale = _fp_scale_val(tag)
        if scale is not None:
            return max(0.0, min(1.0, scale))
        if b_core and b_core.endswith("1"):
            return 0.0
        return 1.0

    def _size_for_spp(spp):
        """SPP → marker size. Small for x1, growing with SPP."""
        # Map x1→24, x4→32, x8→40, x16→48 (roughly linear in log2).
        import math
        idx = max(0, int(math.log2(max(spp, 1))))
        return 24 + idx * 8

    def _darken_for_spp(color, spp):
        """Combine the size ramp with a darkness ramp on the face color.
        x1 → base hue, higher SPP → progressively darker toward black. Caps
        at 0.6 so x16 is still distinguishable from black. Helps large/dark
        (high-SPP) and small/light (low-SPP) pairs stay linked visually even
        when series are tightly clustered."""
        import math
        idx = max(0, int(math.log2(max(spp, 1))))
        factor = min(0.6, 0.15 * idx)
        rgba = to_rgba(color)
        return (rgba[0] * (1.0 - factor),
                rgba[1] * (1.0 - factor),
                rgba[2] * (1.0 - factor),
                rgba[3])

    def _sort_key(vname):
        a, b_core, tag = _parse(vname)
        if a is None:
            return (99, 99, vname)
        rank = _B.get(b_core, ("o", 99))[1]
        tag_rank = _all_tags.index(tag) if tag in _all_tags else 99
        # Sort order: B-complexity, tag — keeps same-variant different-quant
        # points adjacent in the legend.
        return (rank, tag_rank, vname)

    def _valid(v):
        if v is None: return False
        if include_neg: return True
        return v >= 0

    # A "series" is one unique (variant, spp, warmup_first, warmup_run, subframe_n)
    # tuple — step 01 has 1 variant × 7 sweep configs that need to be separate
    # dots + separate legend entries; other steps typically collapse to the
    # familiar (variant, spp) series since warmup/subframe is constant.
    def _row_key(r):
        return (r["variant"], r["spp"],
                int(r.get("warmup_first") or 0),
                int(r.get("warmup_run")   or 0),
                int(r.get("subframe_n")   or 1))
    series_keys = sorted({_row_key(r) for r in rows},
                         key=lambda k: (_sort_key(k[0]), k[1], k[4], k[2], k[3]))

    # Detect the step-01 case: subframe N and/or warmup slots vary across the
    # series set. Step 01 keeps a single variant name but sweeps (sn, w1, wr),
    # so those axes need extra encoding (marker per sn, hue ramp across
    # warmup). Elsewhere sn and warmup are constant across the sweep, so the
    # B-core / hue_key encoding carries everything.
    _sn_varies     = len({k[4] for k in series_keys}) > 1
    _warmup_varies = len({(k[2], k[3]) for k in series_keys}) > 1
    _subframe_step = _sn_varies or _warmup_varies

    variant_series_count = {}
    for k in series_keys:
        variant_series_count[k[0]] = variant_series_count.get(k[0], 0) + 1
    idx_within_variant = {}
    seen = {}
    for k in series_keys:
        i = seen.get(k[0], 0)
        idx_within_variant[k] = i
        seen[k[0]] = i + 1

    n_sc    = len(scenes)
    scene_x = {s: i for i, s in enumerate(scenes)}
    all_x   = n_sc + 0.4  # gap before the "All" column, matching inter-scene margin

    n_series = len(series_keys)
    spread   = 0.35
    offsets  = np.linspace(-spread / 2, spread / 2, n_series) if n_series > 1 else [0.0]

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(max(7, (n_sc + 2) * 2.0), 5))
    else:
        fig = ax.figure

    legend_handles = []
    any_point = False
    has_whiskers = whisker_blob_key is not None
    for series_idx, key in enumerate(series_keys):
        vname, spp, w1, wr, sn = key
        marker, color = _style(vname)
        alpha = _alpha(vname)
        # When the same variant name repeats across many sweep configs and no
        # tag-based hue applies (step 01's warmup/subframe sweep): encode
        # subframe N via marker (star / square / triangle-up) and the warmup
        # position (0 / 1 / half-cycle) via a shared viridis hue ramp — so the
        # three warmup points of 2×2 share the same gradient as those of 4×4.
        # Step 01 (subframe/warmup sweep): encode subframe N via marker —
        # N=1 is the oversized crimson star (cold-start, unmistakable);
        # N=2 = square; N=4 = triangle-up. Hue encodes warmup position via a
        # viridis ramp so corresponding warmup points read the same color
        # across the N=2 and N=4 families (0 / 1 / half-cycle → 0 / 0.5 / 1).
        if _subframe_step and not _hue_keys:
            peers = sorted({(k[2], k[3]) for k in series_keys if k[0] == vname and k[4] == sn})
            try:
                rank = peers.index((w1, wr))
            except ValueError:
                rank = 0
            t = rank / max(1, len(peers) - 1)
            color = plt.cm.viridis(0.15 + 0.70 * t)
            if sn == 2:
                marker = "s"
            elif sn == 4:
                marker = "^"
            if sn == 1:
                marker = "*"
                color  = "#d62728"  # crimson — cold-start, unmistakable
        # SPP ramp: higher SPP darkens both edge and face so size+darkness
        # pair consistently across the whole marker.
        face_rgba = _darken_for_spp(color, spp)
        # Fill alpha encodes fp scale (0 = hollow, 1 = solid, 0.5 = half).
        fill_alpha = _fp_alpha(vname)
        fc = "none" if fill_alpha <= 0.01 else (face_rgba[0], face_rgba[1], face_rgba[2], fill_alpha)
        size   = _size_for_spp(spp)
        # Step 01 N=1 gets an extra size bump so the cold-start star dominates.
        if _subframe_step and not _hue_keys and sn == 1:
            size = size + 40
            fc   = face_rgba  # solid crimson fill regardless of fp_alpha
        label_parts = [vname, f"x{spp}"]
        subframe_part = f"{sn}x{sn}" if sn > 1 else ""
        warmup_part   = f"w{w1}|{wr}" if (w1 or wr) else ""
        if subframe_part or warmup_part:
            label_parts.append(subframe_part + warmup_part)
        label = " ".join(label_parts)

        pts, whiskers = [], []
        for r in rows:
            if _row_key(r) != key or not _valid(r.get(metric_key)):
                continue
            x = scene_x[r["scene"]] + offsets[series_idx]
            y = r[metric_key]
            pts.append((x, y))
            if has_whiskers:
                blob = r.get(whisker_blob_key)
                if blob is not None:
                    # Positive-only degradation blob — clamp ≤0 at display so
                    # older CSVs (signed-magnitude blob) match the new metric.
                    blob = max(0.0, float(blob))
                    if blob > 0:
                        whiskers.append((x, y, blob))

        # "All" column: mean across scenes; whisker tip = worst positive blob.
        scene_means, scene_blobs = [], []
        for s in scenes:
            matching = [r for r in rows
                        if _row_key(r) == key and r["scene"] == s and _valid(r.get(metric_key))]
            if not matching:
                continue
            scene_means.append(float(np.mean([r[metric_key] for r in matching])))
            if has_whiskers:
                blobs = [max(0.0, float(r[whisker_blob_key]))
                         for r in matching if r.get(whisker_blob_key) is not None]
                blobs = [b for b in blobs if b > 0]
                if blobs:
                    scene_blobs.append(max(blobs))
        if scene_means:
            x_all = all_x + offsets[series_idx]
            mean_all = float(np.mean(scene_means))
            pts.append((x_all, mean_all))
            if has_whiskers and scene_blobs:
                whiskers.append((x_all, mean_all, max(scene_blobs)))

        if not pts:
            continue
        # End-marker tick size scales with the point size so it reads across
        # the small (x1) / large (x16) symbol sizes in the same chart.
        tick_half = 0.025 + 0.0004 * size
        for (wx, wlo, whi) in whiskers:
            ax.vlines(wx, wlo, whi, color=color, alpha=0.5 * alpha, linewidth=1.2, zorder=2)
            ax.hlines(whi, wx - tick_half, wx + tick_half,
                      color=color, alpha=0.7 * alpha, linewidth=1.2, zorder=2)
        xs, ys = zip(*pts)
        # No scalar `alpha` — RGBA tuples in facecolors carry per-marker face
        # alpha (edge stays solid via full-alpha edgecolors). Both edge and
        # face share the SPP darkness ramp so the size+darkness pair reads
        # consistently across the whole marker, not just its fill.
        h = ax.scatter(xs, ys, label=label, marker=marker,
                       edgecolors=face_rgba, facecolors=fc,
                       linewidths=1.2, s=size, zorder=3)
        legend_handles.append(h)
        any_point = True

    if not any_point:
        if own_fig:
            plt.close(fig)
        return None

    ax.set_xticks(list(range(n_sc)) + [all_x])
    ax.set_xticklabels([s.replace("CornellBox_", "") for s in scenes] + ["All"],
                       rotation=20, ha="right", fontsize=9)
    ax.axvline(x=n_sc - 0.5, color="#bbbbbb", linestyle="--", linewidth=0.8, zorder=1)

    if zero_line:
        ax.axhline(y=0, color="#666666", linestyle="-", linewidth=0.8, zorder=2)

    ax.set_ylabel(ylabel)
    # Per-axis title sits directly above the plot area for every plot (single
    # or combined panel); figure suptitle carries the step + theme once.
    ax.set_title(title_suffix, fontsize=10, loc="left")
    if own_fig:
        step_main = _step_title(step_name)
        suptitle = f"Step {step_name}" + (f" — {step_main}" if step_main else "")
        if prev_winner:
            suptitle += f"   [base = {prev_winner}]"
        fig.suptitle(suptitle, fontsize=11)
        ax.legend(handles=legend_handles, fontsize=6,
                  loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0, ncol=1)
    if symlog_linthresh is not None:
        # Symmetric log: [-linthresh, +linthresh] is linear, values beyond
        # compress logarithmically. linscale < 1 shrinks the linear band's
        # visual share, pulling the 10¹/10² decades in closer to zero so
        # typical ±1-100% whiskers don't dominate the y-axis visually while
        # sub-linthresh detail near 0 still reads.
        ax.set_yscale("symlog", linthresh=symlog_linthresh, linscale=0.5)
        # Plain decimals on the axis (no 1e1/1e2 scientific notation). Minor
        # ticks also use ScalarFormatter so intermediate labels read cleanly.
        from matplotlib.ticker import ScalarFormatter
        fmt = ScalarFormatter()
        fmt.set_scientific(False)
        ax.yaxis.set_major_formatter(fmt)
        ax.yaxis.set_minor_formatter(ScalarFormatter(useOffset=False))
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", alpha=0.15)

    if not save or not own_fig:
        return legend_handles  # caller manages fig + file I/O

    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"overview_{out_suffix}_{step_name}.png")
    # bbox_inches='tight' keeps external legends visible without clipping.
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[overview] {out}")
    return out


def plot_overviews(step_name, prev_winner=None):
    """Generates three overview scatter plots per step:
      overview_rays_<step>.png   — rays traced %
      overview_error_<step>.png  — signed GT-error Δ vs vanilla %
      overview_noise_<step>.png  — absolute mean OkLab distance to GT, % of viridis max
    Returns list of paths (may contain None entries for metrics with no data).
    """
    import csv

    csv_path = _step_csv(step_name)
    if not os.path.exists(csv_path):
        print(f"[overview] No stats CSV yet: {csv_path}")
        return None

    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            # Required fields; skip malformed rows.
            try:
                row["rays_traced_pct"] = float(row["rays_traced_pct"])
            except (ValueError, KeyError):
                continue
            # Optional numeric fields — empty string → None
            for k in ("coldmiss_pct",
                      "error_delta_pct", "error_delta_min_pct", "error_delta_max_pct",
                      "error_delta_blob_pct",
                      "noise_delta_pct", "noise_delta_min_pct", "noise_delta_max_pct",
                      "noise_delta_blob_pct"):
                v = row.get(k, "")
                try:
                    row[k] = float(v) if v not in ("", None) else None
                except ValueError:
                    row[k] = None
            # spp may be absent in older CSVs — fall back to 1
            try:
                row["spp"] = int(row.get("spp") or 1)
            except ValueError:
                row["spp"] = 1
            rows.append(row)

    if not rows:
        print(f"[overview] No data in {csv_path}")
        return None

    out_rays  = _plot_metric(rows, step_name, "rays_traced_pct",
                             ylabel="rays traced %", title_suffix="rays traced",
                             out_suffix="rays", ylim=RAYS_YLIM, prev_winner=prev_winner)
    out_err   = _plot_metric(rows, step_name, "error_delta_pct",
                             ylabel="error Δ % (symlog)", title_suffix="error Δ (whisker: max blob)",
                             out_suffix="error", zero_line=True, include_neg=True,
                             whisker_blob_key="error_delta_blob_pct",
                             ylim=ERROR_DELTA_YLIM,
                             symlog_linthresh=1.0, prev_winner=prev_winner)
    out_noise = _plot_metric(rows, step_name, "noise_delta_pct",
                             ylabel="noise Δ % (symlog)", title_suffix="noise Δ",
                             out_suffix="noise", zero_line=True, include_neg=True,
                             ylim=NOISE_DELTA_YLIM,
                             symlog_linthresh=1.0, prev_winner=prev_winner)
    out_combined = _plot_combined(rows, step_name, prev_winner=prev_winner)
    return [out_rays, out_err, out_noise, out_combined]


def _plot_combined(rows, step_name, prev_winner=None):
    """3-panel stacked plot sharing x-axis: rays (top), error Δ (mid), noise Δ (bottom).
    Each panel uses _plot_metric with whiskers on the signed metrics. Single legend
    on the right applies to all three panels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenes = sorted(set(r["scene"] for r in rows))
    n_sc = len(scenes)
    fig, axes = plt.subplots(3, 1,
                             figsize=(max(7, (n_sc + 2) * 2.0), 10),
                             sharex=True,
                             constrained_layout=True)

    _plot_metric(rows, step_name, "rays_traced_pct",
                 ylabel="rays traced %", title_suffix="rays traced",
                 out_suffix="rays", ylim=RAYS_YLIM,
                 ax=axes[0], save=False)
    _plot_metric(rows, step_name, "error_delta_pct",
                 ylabel="error Δ % (symlog)", title_suffix="error Δ (whisker: max blob)",
                 out_suffix="error", zero_line=True, include_neg=True,
                 whisker_blob_key="error_delta_blob_pct",
                 ylim=ERROR_DELTA_YLIM,
                 symlog_linthresh=1.0,
                 ax=axes[1], save=False)
    legend_handles = _plot_metric(rows, step_name, "noise_delta_pct",
                                  ylabel="noise Δ % (symlog)", title_suffix="noise Δ",
                                  out_suffix="noise", zero_line=True, include_neg=True,
                                  ylim=NOISE_DELTA_YLIM,
                                  symlog_linthresh=1.0,
                                  ax=axes[2], save=False)

    step_main = _step_title(step_name)
    suptitle = f"Step {step_name}" + (f" — {step_main}" if step_main else "")
    if prev_winner:
        suptitle += f"   [base = {prev_winner}]"
    fig.suptitle(suptitle, fontsize=11)
    if isinstance(legend_handles, list) and legend_handles:
        # Legend's upper-left anchored just past the figure's right edge →
        # fully outside the plot area, top-right. bbox_inches='tight' at
        # savefig expands the bounding box to include it.
        fig.legend(handles=legend_handles, fontsize=6,
                   loc="upper left", bbox_to_anchor=(1.02, 1.0),
                   borderaxespad=0, ncol=1)

    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"overview_summary_{step_name}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[overview] {out}")
    return out


def _plot_baseline_metric(rows, metric_key, ylabel, title_suffix, out_suffix,
                          max_key=None, ax=None, save=True):
    """Scatter for step 00 baselines: scenes on x-axis, one series per SPP.

    No variants — just the vanilla reference at different sample counts.
    Hue & size encode SPP (dark/small = x1, bright/large = x4096). Optional
    max_key overlays a whisker from mean to max-blob (for error's max stat).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    _SCENE_ORDER = [
        "CornellBox_1PointLight",
        "CornellBox_1AreaLight",
        "CornellBox_3AreaLights",
        "CornellBox_32PointLights",
    ]
    def _scene_key(s):
        return (_SCENE_ORDER.index(s), s) if s in _SCENE_ORDER else (len(_SCENE_ORDER), s)
    scenes = sorted({r["scene"] for r in rows}, key=_scene_key)
    spps   = sorted(set(r["spp"] for r in rows))

    n_sc    = len(scenes)
    scene_x = {s: i for i, s in enumerate(scenes)}
    all_x   = n_sc + 0.2

    n_series = len(spps)
    spread   = 0.35
    offsets  = np.linspace(-spread/2, spread/2, n_series) if n_series > 1 else [0.0]

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(max(7, (n_sc + 2) * 2.0), 5))
    else:
        fig = ax.figure

    def _spp_color(spp):
        idx = spps.index(spp)
        return plt.cm.viridis(0.1 + 0.8 * idx / max(1, len(spps) - 1))

    def _size_for_spp(spp):
        import math
        idx = max(0, int(math.log2(max(spp, 1))))
        return 24 + idx * 4

    legend_handles = []
    for i, spp in enumerate(spps):
        color = _spp_color(spp)
        size  = _size_for_spp(spp)
        xs, ys, y_maxs = [], [], []
        scene_vals, scene_maxs = {}, {}
        for r in rows:
            if r["spp"] != spp: continue
            v = r.get(metric_key)
            if v is None: continue
            xs.append(scene_x[r["scene"]] + offsets[i])
            ys.append(v)
            scene_vals[r["scene"]] = v
            if max_key is not None:
                mv = r.get(max_key)
                if mv is not None:
                    scene_maxs[r["scene"]] = mv
                    y_maxs.append(mv)
        tick_half = 0.025 + 0.0004 * size
        if max_key is not None and y_maxs:
            for x, ymean, ymax in zip(xs, ys, y_maxs):
                ax.vlines(x, ymean, ymax, colors=[color], linewidths=1.0,
                          alpha=0.6, zorder=2)
                ax.hlines(ymax, x - tick_half, x + tick_half,
                          colors=[color], linewidths=1.2, alpha=0.7, zorder=2)
        h = ax.scatter(xs, ys, s=size, c=[color], marker="o",
                       edgecolors="black", linewidths=0.5, zorder=3,
                       label=f"x{spp}")
        legend_handles.append(h)
        if scene_vals:
            mean_all = float(np.mean(list(scene_vals.values())))
            if max_key is not None and scene_maxs:
                max_all = float(np.mean(list(scene_maxs.values())))
                xa = all_x + offsets[i]
                ax.vlines(xa, mean_all, max_all,
                          colors=[color], linewidths=1.0, alpha=0.6, zorder=2)
                ax.hlines(max_all, xa - tick_half, xa + tick_half,
                          colors=[color], linewidths=1.2, alpha=0.7, zorder=2)
            ax.scatter([all_x + offsets[i]], [mean_all], s=size, c=[color],
                       marker="o", edgecolors="black", linewidths=0.5, zorder=3)

    ax.axvline(n_sc - 0.5 + 0.6, color="#888", linewidth=0.5, alpha=0.5, zorder=1)
    ax.set_xticks(list(range(n_sc)) + [all_x])
    ax.set_xticklabels([s.replace("CornellBox_", "") for s in scenes] + ["All"],
                       rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_yscale("symlog", linthresh=1.0, linscale=0.5)
    # Consistent absolute-metric ylim across step-00 plots: the unsigned
    # error/noise % sweep gets the same ceiling as its signed-delta cousin
    # in the later steps so the two are visually comparable.
    if metric_key == "mean_err_pct":
        ax.set_ylim(*ERROR_ABS_YLIM)
    elif metric_key == "mean_noise_pct":
        ax.set_ylim(*NOISE_ABS_YLIM)
    else:
        ax.set_ylim(bottom=0)
    # Plain decimal tick labels (no 1e1/1e2 scientific notation).
    from matplotlib.ticker import ScalarFormatter
    fmt = ScalarFormatter()
    fmt.set_scientific(False)
    ax.yaxis.set_major_formatter(fmt)
    ax.yaxis.set_minor_formatter(ScalarFormatter(useOffset=False))
    ax.grid(True, alpha=0.3)
    ax.set_title(title_suffix, fontsize=10)

    if own_fig and save:
        ax.legend(handles=legend_handles, fontsize=7, ncol=2,
                  loc="upper left", bbox_to_anchor=(1.02, 1.0),
                  borderaxespad=0)
        out_dir = "captures/ladder/00"
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"overview_{out_suffix}_00.png")
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[overview] {out}")
        return out
    return legend_handles


def plot_baseline_overviews(step_name="00"):
    """Generates two overview scatter plots for step 00 plus a combined summary:
      overview_error_00.png   — mean/max error vs GT, % of OkLab max
      overview_noise_00.png   — mean bilateral noise, % (floor-subtracted)
      overview_summary_00.png — 2-panel stacked plot sharing x-axis
    """
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    csv_path = _step_csv(step_name)
    if not os.path.exists(csv_path):
        print(f"[overview] No baseline CSV yet: {csv_path}")
        return None

    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if any(k not in row for k in _CSV_BASELINE_FIELDS):
                continue
            try:
                row["spp"] = int(row["spp"])
            except (ValueError, KeyError):
                continue
            for k in ("mean_err_pct", "max_err_pct", "mean_noise_pct"):
                v = row.get(k, "")
                try:
                    row[k] = float(v) if v not in ("", None) else None
                except ValueError:
                    row[k] = None
            rows.append(row)
    if not rows:
        print(f"[overview] No baseline rows in {csv_path}")
        return None

    # Drop the GT self-reference (largest SPP) — it's trivially 0% err / 0%
    # noise by construction and just compresses the visible y-range. Stays in
    # the CSV as a calibration sanity check.
    spps_present = sorted({r["spp"] for r in rows})
    if len(spps_present) > 1:
        gt_spp = spps_present[-1]
        rows = [r for r in rows if r["spp"] != gt_spp]

    out_err   = _plot_baseline_metric(rows, "mean_err_pct",
                                      ylabel="error % (symlog)",
                                      title_suffix="error vs GT (whisker: max blob)",
                                      out_suffix="error", max_key="max_err_pct")
    out_noise = _plot_baseline_metric(rows, "mean_noise_pct",
                                      ylabel="noise % (symlog)",
                                      title_suffix="bilateral noise (floor-subtracted)",
                                      out_suffix="noise")

    n_sc = len({r["scene"] for r in rows})
    fig, axes = plt.subplots(2, 1,
                             figsize=(max(7, (n_sc + 2) * 2.0), 7),
                             sharex=True, constrained_layout=True)
    legend_handles = _plot_baseline_metric(rows, "mean_err_pct",
                                           ylabel="error % (symlog)",
                                           title_suffix="error vs GT (whisker: max blob)",
                                           out_suffix="error", max_key="max_err_pct",
                                           ax=axes[0], save=False)
    _plot_baseline_metric(rows, "mean_noise_pct",
                          ylabel="noise % (symlog)",
                          title_suffix="bilateral noise (floor-subtracted)",
                          out_suffix="noise",
                          ax=axes[1], save=False)
    step_main = _step_title(step_name)
    suptitle = f"Step {step_name}" + (f" — {step_main}" if step_main else "")
    fig.suptitle(suptitle, fontsize=11)
    if isinstance(legend_handles, list) and legend_handles:
        fig.legend(handles=legend_handles, fontsize=7,
                   loc="upper left", bbox_to_anchor=(1.02, 1.0),
                   borderaxespad=0, ncol=1)
    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"overview_summary_{step_name}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[overview] {out}")
    return [out_err, out_noise, out]


def finalize_baseline(step_name="00"):
    """Step-00 end-of-run footer: emit baseline overview plots and mirror the
    summary PNG to the ladder root. Baseline analogue of `finalize_step` for
    absolute (non-delta) error/noise metrics."""
    plot_baseline_overviews(step_name)
    copy_summary_to_root(step_name)


def finalize_step(step_name, prev_winner=None):
    """Standard end-of-step footer: emit the per-metric overview plots and
    mirror the summary PNG to the ladder root. Replaces the repeated
    `plot_overviews(STEP); copy_summary_to_root(STEP)` pair in each script.

    prev_winner: optional variant name forwarded to plot_overviews so the
    step's title records the variant it inherited from the prior sweep.
    """
    plot_overviews(step_name, prev_winner=prev_winner)
    copy_summary_to_root(step_name)


def copy_summary_to_root(step_name):
    """Mirror captures/ladder/<step>/overview_summary_<step>.png into captures/ladder/
    so every step's summary sits at one level for cross-step comparison.
    Silent no-op if the source summary doesn't exist yet."""
    src = os.path.join(f"captures/ladder/{step_name}",
                       f"overview_summary_{step_name}.png")
    dst = os.path.join("captures/ladder", f"overview_summary_{step_name}.png")
    if not os.path.exists(src):
        return None
    try:
        shutil.copy2(src, dst)
        print(f"[summary] {dst}")
        return dst
    except (IOError, OSError):
        return None


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
    # Raw EXRs live either directly in captureDir (fresh capture) or under
    # captureDir/raw/ (post-archival — when re-running postprocess standalone).
    exrs = glob.glob(os.path.join(captureDir, f"{vn}.*.exr")) \
         + glob.glob(os.path.join(captureDir, "raw", f"{vn}.*.exr"))

    # No-data masks: accum (fractional, from count+coldmissRate) vs frame (binary, from hashA+B==0)
    nd_accum = load_diag_mask(exrs, mode="nodata", total_frames=total_frames)
    nd_frame = load_diag_mask(exrs, mode="nodata_frame")

    # --- Compute global stats from EXR data ---
    stats = {"rays_traced_pct": -1.0, "coldmiss_pct": -1.0,
             "error_delta_pct": None, "error_delta_min_pct": None, "error_delta_max_pct": None,
             "error_delta_blob_pct": None, "noise_delta_blob_pct": None,
             "noise_delta_pct": None, "noise_delta_min_pct": None, "noise_delta_max_pct": None}
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
    # Raw ToneMapper output: live in captureDir on fresh capture, moved into
    # raw/ after the archive step. Copy the first we find.
    tm_srcs = glob.glob(os.path.join(captureDir, f"{vn}.ToneMapper.dst.*")) \
            + glob.glob(os.path.join(captureDir, "raw", f"{vn}.ToneMapper.dst.*"))
    for src in tm_srcs:
        render_path = o("r1c1_accum_render")
        shutil.copy2(src, render_path)
        break

    # --- HDR baseline comparisons from step 00 ---
    scene_name = os.path.basename(captureDir)
    baseline_dir = os.path.join(os.path.dirname(captureDir), "..", "00", scene_name)

    # Find variant's HDR EXR (pre-tonemapper) — either live or archived.
    variant_hdr = find_exr(
        glob.glob(os.path.join(captureDir, f"{vn}.*"))
      + glob.glob(os.path.join(captureDir, "raw", f"{vn}.*")),
        "AccumulatePass.output")

    # GT baselines for both error (signed Δ) and noise (absolute).
    gt_baselines = sorted(glob.glob(os.path.join(baseline_dir, "*_vanilla_hdr.exr")))
    gt_baselines = [b for b in gt_baselines if "_x1_" not in b]
    vanilla_xN_baselines = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_hdr.exr"))

    # Error Δ (r1c3): perceptual GT-error delta — OkLabDistance(viscache, GT) − OkLabDistance(vanilla_xN, GT).
    # Negative (purple→black) = VisCache denoised; positive (viridis) = degraded.
    # Vanilla-vs-GT map is identical across variants at the same scene+SPP — loaded
    # from the .npy cache seeded by step 00's GT-err PNG generation.
    if variant_hdr and vanilla_xN_baselines and gt_baselines:
        vanilla_xN_hdr = vanilla_xN_baselines[0]
        vanilla_err_cache = vanilla_xN_hdr.replace("_vanilla_hdr.exr", "_vanilla_gterr.npy")
        if not os.path.exists(vanilla_err_cache):
            vanilla_err_cache = None  # step 00 hasn't populated the cache — recompute
        r = compute_render_error_signed_hdr(variant_hdr, vanilla_xN_hdr, gt_baselines[-1],
                                            o("r1c3_accum_error"),
                                            vanilla_err_cache=vanilla_err_cache)
        if r is not None:
            stats["error_delta_pct"]      = r["err_delta_pct"]
            stats["error_delta_min_pct"]  = r["err_delta_min_pct"]
            stats["error_delta_max_pct"]  = r["err_delta_max_pct"]
            stats["error_delta_blob_pct"] = r.get("err_delta_blob_pct")
        print(f"  [error] {os.path.basename(o('r1c3_accum_error'))}")
    elif variant_hdr and vanilla_xN_baselines:
        # No GT: fall back to absolute |viscache - vanilla_xN|
        from viscache_exr import compute_render_error_hdr
        compute_render_error_hdr(variant_hdr, vanilla_xN_baselines[0], o("r1c3_accum_error"))
        print(f"  [error] {os.path.basename(o('r1c3_accum_error'))} (no GT, falling back to |viscache - vanilla_xN|)")
    elif render_path:
        error_baseline = glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_r1c1_accum_render.png"))
        if error_baseline:
            compute_render_error(render_path, error_baseline[0], o("r1c3_accum_error"))
            print(f"  [error] {os.path.basename(o('r1c3_accum_error'))} (PNG fallback)")

    # Noise Δ (r1c9): signed bilateral-noise delta — bilateral_noise(viscache LDR)
    # − bilateral_noise(vanilla_xN LDR). Measures screen-space noise difference
    # independent of GT. Negative = VisCache smoother; positive = noisier.
    vanilla_xN_renders = sorted(glob.glob(os.path.join(baseline_dir, f"*_x{spp}_*_vanilla_r1c1_accum_render.png")))
    if render_path and vanilla_xN_renders:
        r = compute_render_noise_signed(render_path, vanilla_xN_renders[0], o("r1c9_accum_noise"))
        if r is not None:
            stats["noise_delta_pct"]      = r["noise_delta_pct"]
            stats["noise_delta_min_pct"]  = r["noise_delta_min_pct"]
            stats["noise_delta_max_pct"]  = r["noise_delta_max_pct"]
            stats["noise_delta_blob_pct"] = r.get("noise_delta_blob_pct")
        print(f"  [noise] {os.path.basename(o('r1c9_accum_noise'))}")
    elif render_path:
        compute_render_noise(render_path, o("r1c9_accum_noise"))
        print(f"  [noise] {os.path.basename(o('r1c9_accum_noise'))} (absolute fallback, no baseline)")

    # Archive raw EXRs + tonemapped output into captureDir/raw/ so the whole
    # postprocess stage (PNGs, plate, stats) can be regenerated later without
    # re-rendering. See VisCache_Repostprocess.py.
    raw_dir = os.path.join(captureDir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    for f in exrs:
        try:
            shutil.move(f, os.path.join(raw_dir, os.path.basename(f)))
        except (PermissionError, OSError):
            pass
    for f in glob.glob(os.path.join(captureDir, f"{vn}.*")):
        if not f.endswith(".png"):
            continue
        # Grid-named PNGs (with {prefix}r1c/r2c prefix) stay in captureDir;
        # raw Mogwai ToneMapper PNGs go into raw/ for reference (source for
        # render_path / noise metric on re-postprocess).
        if os.path.basename(f).startswith(prefix):
            continue
        try:
            shutil.move(f, os.path.join(raw_dir, os.path.basename(f)))
        except (PermissionError, OSError):
            pass

    return stats


def postprocess_variant(step_name, scene_name, capture_dir, prefix, variant_name,
                         frames, spp, warmup_first, warmup_run, subframe_n,
                         resX=kResX, resY=kResY):
    """Run the full per-variant post-capture pipeline — PNG extraction via
    postprocess(), plate stitch, CSV upsert — then annotate the stats dict
    for overview plotting. Shared between the live-render path (run_variants,
    called right after a capture) and the offline re-post-process path
    (VisCache_Repostprocess.py, called after the fact from archived raw/ EXRs).

    total_frames  = frames. PathTracer handles N² Bayer sub-dispatches
                    internally per renderFrame, so each logical frame produces
                    exactly `frames` diagnostic counter increments per pixel.
    effective_spp = frames × spp — used by postprocess to look up matched-SPP
                    baselines; e.g. (frames=16, spp=1) and (frames=1, spp=16)
                    both map to the vanilla_x16 reference.
    """
    total_frames  = frames
    effective_spp = frames * spp

    stats = postprocess(capture_dir, prefix, variant_name,
                        total_frames=total_frames, spp=effective_spp,
                        resX=resX, resY=resY)
    stitch_plate(capture_dir, prefix, variant_name, stats=stats)

    append_stats_csv(
        step_name, scene_name, prefix, variant_name,
        spp, frames, warmup_first, warmup_run, subframe_n,
        stats["rays_traced_pct"], stats["coldmiss_pct"],
        stats.get("error_delta_pct"),
        stats.get("error_delta_min_pct"), stats.get("error_delta_max_pct"),
        stats.get("error_delta_blob_pct"),
        stats.get("noise_delta_pct"),
        stats.get("noise_delta_min_pct"), stats.get("noise_delta_max_pct"),
        stats.get("noise_delta_blob_pct"),
    )

    stats["variant"] = variant_name
    stats["scene"]   = scene_name
    stats["spp"]     = spp
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
            # frames:      logical frame count. PathTracer internally loops N² Bayer
            #              subframes per renderFrame (see PathTracer.cpp commit 432d4c6)
            #              so one renderFrame call = one fully composed dense logical frame.
            warmupFirst, warmupRun, frames = fc_entry[0], fc_entry[1], fc_entry[2]
            spp = fc_entry[3] if len(fc_entry) > 3 else 1
            subN = overrides.get("subframeN", 1)
            render_frames = frames
            tag = f"s_{frames}_x{spp}_{warmupFirst}o{warmupRun}o{subN}x{subN}_{res_tag}"
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
            stats = postprocess_variant(
                step_name, scene_name, captureDir, pfx, variant_name,
                frames=frames, spp=spp,
                warmup_first=warmupFirst, warmup_run=warmupRun, subframe_n=subN,
                resX=resX, resY=resY,
            )
            all_stats.append(stats)

            m.removeGraph(g)

    print(f"\n[{step_name}] All done.")
    return all_stats


def _baseline_noise_floor(captureDir, gt_spp, res_tag):
    """Compute + cache GT self-noise for a baseline capture directory.

    The x4096 bilateral noise map is subtracted from every lower-SPP noise plate
    (clamped ≥0) — the residual bilateral CoV in the converged reference is the
    detector's own response to edge aliasing, not MC noise. Returns the cached
    numpy array, or None if the GT render PNG is missing."""
    from viscache_exr import bilateral_noise_cached
    gt_render       = os.path.join(captureDir, f"s_x{gt_spp}_{res_tag}_vanilla_r1c1_accum_render.png")
    noise_floor_npy = os.path.join(captureDir, f"s_x{gt_spp}_{res_tag}_vanilla_noise_floor.npy")
    if not os.path.exists(gt_render):
        return None
    return bilateral_noise_cached(gt_render, cache_path=noise_floor_npy)


def postprocess_baseline_spp(step_name, captureDir, scene_name,
                              spp, res_tag, gt_hdr, noise_floor):
    """Per-SPP baseline postprocess: error PNG, noise PNG, plate, CSV row.

    Shared helper — called from both run_baseline (live capture) and
    VisCache_Replate00 (offline regen from existing EXRs). Silent no-op if the
    SPP's HDR / render PNG are missing. Returns (err_stats, noise_stats).
    """
    from viscache_exr import compute_render_error_hdr, compute_render_noise

    xN_tag    = f"s_x{spp}_{res_tag}"
    xN_hdr    = os.path.join(captureDir, f"{xN_tag}_vanilla_hdr.exr")
    xN_render = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c1_accum_render.png")
    if not os.path.exists(xN_hdr) or not os.path.exists(xN_render):
        return None, None

    err_path   = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c3_accum_error.png")
    dist_cache = os.path.join(captureDir, f"{xN_tag}_vanilla_gterr.npy")
    err_stats = compute_render_error_hdr(xN_hdr, gt_hdr, err_path, distance_cache=dist_cache)
    if err_stats is not None:
        # ASCII-only — Mogwai's stdout is cp1252 on Windows.
        print(f"[{step_name}] [GT-err] vanilla_x{spp}: "
              f"mean={err_stats['mean_err_pct']:.2f}% max={err_stats['max_err_pct']:.2f}% "
              f"-> {os.path.basename(err_path)}")

    noise_path = os.path.join(captureDir, f"{xN_tag}_vanilla_r1c9_accum_noise.png")
    noise_stats = compute_render_noise(xN_render, noise_path, floor=noise_floor)
    if noise_stats is not None:
        print(f"[{step_name}] [noise]  vanilla_x{spp}: "
              f"mean={noise_stats['mean_noise_pct']:.2f}% "
              f"-> {os.path.basename(noise_path)}")

    plate_out = os.path.join(os.path.dirname(captureDir),
                             f"{scene_name}_{xN_tag}_vanilla_plate.png")
    stitch_baseline_plate(captureDir, xN_tag, plate_out,
                           err_stats=err_stats, noise_stats=noise_stats)

    append_baseline_csv(
        step_name, scene_name, spp,
        mean_err_pct   = err_stats.get("mean_err_pct")   if err_stats   else None,
        max_err_pct    = err_stats.get("max_err_pct")    if err_stats   else None,
        mean_noise_pct = noise_stats.get("mean_noise_pct") if noise_stats else None,
    )
    return err_stats, noise_stats


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
            # Vanilla tag depends only on virtual SPP (total samples/pixel) — the
            # outer `frames` loop multiplies the sample count but isn't exposed in
            # the tag because comparisons key on virtual SPP alone.
            tag = f"s_x{spp}_{res_tag}"
            out_path = _out(captureDir, "r1c1_accum_render", f"{tag}_vanilla_")

            if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                print(f"\n[{step_name}] ======== vanilla_x{spp} {tag} ({scene_name}) - cached ========")
                continue

            print(f"\n[{step_name}] ======== vanilla_x{spp} {tag} ({scene_name}) ========")

            # Remap virtual SPP to Falcor params.
            # - Non-GT (spp <= 16): multi-frame × 1 SPP with per-frame jitter.
            #   Matches VisCache tests' frames-based sample accumulation so the
            #   vanilla baseline is apples-to-apples under concurrent-write
            #   semantics that VisCache stresses.
            # - GT (spp > 16): multi-frame × 16 SPP, camera jitter disabled.
            #   In-sample jitter (sample-generator RNG) covers the pixel; camera
            #   locked to prevent feature drift across accumulated frames.
            if spp <= 16:
                actual_spp = 1
                num_frames = spp
            else:
                actual_spp = 16
                num_frames = max(1, spp // actual_spp)
            # Camera jitter ALWAYS on. High-sample GT gets antialiased by
            # per-frame jitter drift; each frame's stratified samples land
            # on different sub-pixel positions so the accumulated render
            # smooths silhouette edges. With jitter disabled the GT had
            # persistent edge-aliasing that the bilateral-noise detector
            # mis-reported as "noise floor".
            g = render_graph_PathTracer(viscache=False, maxBounces=maxBounces,
                                         samplesPerPixel=actual_spp, useJitter=True)
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

        # After all SPPs rendered for this frame_config: per-baseline plates
        # (render | error vs GT | bilateral noise − self-floor). Also produces
        # the underlying GT-error and noise PNGs as a side effect.
        #
        # The gt_spp self-reference plate is a calibration sanity check — it
        # compares x4096 to itself (error trivially 0) and subtracts the
        # cached self-noise (plate should read 0). Non-zero residuals reveal
        # metric quirks before they contaminate variant deltas.
        gt_hdr_candidates = glob.glob(os.path.join(captureDir, f"s_x{gt_spp}_{res_tag}_vanilla_hdr.exr"))
        gt_hdr = gt_hdr_candidates[0] if gt_hdr_candidates else None
        if gt_hdr:
            noise_floor = _baseline_noise_floor(captureDir, gt_spp, res_tag)
            for spp in spp_list:
                postprocess_baseline_spp(step_name, captureDir, scene_name,
                                          spp, res_tag, gt_hdr, noise_floor)

    print(f"\n[{step_name}] All done.")
