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
    to rebind scene resources to the new render graph's passes.

    After load, explicitly select our VisCacheDefault camera when present so
    FBX-embedded cameras (e.g. Bistro has animated cameras baked in) don't
    get picked up and make the camera viewpoint drift between runs.
    """
    m.loadScene(resolve_scene(scene_file))
    m.resizeFrameBuffer(resX, resY)
    try:
        scene = m.scene
        if scene is not None:
            # Force-select VisCacheDefault via the scene.camera setter
            # (pybind binding: scene.def_property("camera", getCamera, setCamera)
            # where setCamera finds the matching camera and calls selectCamera).
            cameras = getattr(scene, 'cameras', None) or []
            for cam in cameras:
                if getattr(cam, 'name', None) == 'VisCacheDefault':
                    scene.camera = cam
                    break
            # Disable scene animation so the selected camera doesn't drift
            # across successive renderFrame calls (scene clock advances per
            # frame; any animated camera including via parenting would move).
            scene.animated = False
    except (AttributeError, RuntimeError) as e:
        print(f"[scene-camera-lock] warning: {e}")

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

MULTI_LEVEL_SCENES = [
    "CornellBox_32PointLights.pyscene",
    "BistroInterior.pyscene",
    "BistroExterior.pyscene",
    "Sponza.pyscene",
]

def get_scenes(default=None):
    """Resolve scene list from env vars.
    SCENES (comma-separated) > SCENE_FILE (single) > `default` (or ALL_SCENES).
    """
    scenes_env = os.environ.get("SCENES", "")
    if scenes_env:
        return [s.strip() for s in scenes_env.split(",") if s.strip()]
    scene_file = os.environ.get("SCENE_FILE", "")
    if scene_file:
        return [scene_file]
    return default if default is not None else ALL_SCENES

# ===========================================================================
# Building blocks — combine to assemble step configs
# ===========================================================================

# --- Levels ----------------------------------------------------------------
LEVELS_SINGLE = {"numLevels": 1, "autoTuneCells": False}
# 32 levels span coarse→fine geometrically (factor 1024×, ~25% per level).
# Lookup/insert visit a fixed window around the analytical entry level
# (target − A, target + B) — see vhfLookup. With small N, no stride is
# needed and every ray hashes to the same level indices for the same
# world-space cell.
LEVELS_MULTI  = {"numLevels": 32, "autoTuneCells": True}

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
# Single float knob (C++ member `footprintScale`). 0 = disabled (pure
# bootThreshold); 1 = log2(cellPixels) floor; values >1 put more pressure on
# big cells. Default is 0 (baked into PRESET_MINIMAL) — multi-level steps
# take over cell-size modulation and opt in via FOOTPRINT_ON.
FOOTPRINT_ON = {"bootThresholdFactorFootprintPx": 1.0}

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
    "qa003": {"posA": 0.03, "normalA": 60.0, "posB": 0.09, "dirB":  4.0, "distB": 0.12},
    "qa006": {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB":  8.0, "distB": 0.24},
    "qa012": {"posA": 0.12, "normalA": 60.0, "posB": 0.36, "dirB": 15.0, "distB": 0.48},
    "qa036": {"posA": 0.36, "normalA": 60.0, "posB": 1.08, "dirB": 45.0, "distB": 1.44},
}

# Scene-relative quant sizing toggle. When True, quant values are treated
# as fractions of a scene-calibrated reference (Cornell avgAxis = 2). On
# Cornell = 1.0 (values unchanged); larger scenes scale cells proportionally.
SCENE_SCALED_QUANT = {"quantSceneScale": True}

# ===========================================================================
# Assembled presets — named combos of building blocks
# ===========================================================================

# The only preset needed so far — add more when ladder steps demand them.
# footprintScale=0 baked in — multi-level cascade handles cell-size modulation
# so single-level steps never opt into the footprint knob by default.
PRESET_MINIMAL = {**LEVELS_SINGLE, **THRESH_MID, **RR_OFF, **FEATURES_OFF,
                  "bootThresholdFactorFootprintPx": 0.0, **SCENE_SCALED_QUANT}

# ===========================================================================
# Picker + plotter tuning constants
# ===========================================================================

# Scene weights: unweighted across all scenes (per-scene outlier gate
# replaces prior 32PL×3 weighted-mean rule). Kept as an empty dict so
# downstream _scene_weight() returns 1.0 for every scene.
SCENE_WEIGHTS = {}

# Canonical scene ordering for plots + plate filename prefixes. Scenes
# listed here get a 2-digit position prefix (01_, 02_, ...) so plate
# files sort alphabetically into the same order as the plots.
SCENE_ORDER = [
    "CornellBox_1PointLight",
    "CornellBox_1AreaLight",
    "CornellBox_3AreaLights",
    "CornellBox_32PointLights",
    "BistroInterior",
    "BistroExterior",
    "Sponza",
]

def _scene_prefix(scene_name):
    """Return 2-digit position prefix for a scene (e.g. '01_') or empty
    string for unknown scenes."""
    if scene_name in SCENE_ORDER:
        return f"{SCENE_ORDER.index(scene_name) + 1:02d}_"
    return ""

def _scene_weight(scene_name):
    return SCENE_WEIGHTS.get(scene_name, 1.0)

# Per-axis quantization sweep values. Extended by one value per axis
# (doubling step) past the original 3-per-axis set: qA=0.48, qB=1.44,
# qD=60°, qd=1.92. build_per_axis_quant_variants uses these.
PER_AXIS_QA = [0.06, 0.12, 0.24, 0.48]
PER_AXIS_QB = [0.18, 0.36, 0.72, 1.44]
PER_AXIS_QD = [8.0, 15.0, 30.0, 60.0]
PER_AXIS_Qd = [0.24, 0.48, 0.96, 1.92]

# One-liner tag helpers (shared between builder + ladder scripts).
def _qA_tag(v): return f"qA{int(round(v * 100)):03d}"
def _qB_tag(v): return f"qB{int(round(v * 100)):03d}"
def _qD_tag(v): return f"qD{int(round(v)):02d}"
def _qd_tag(v): return f"qd{int(round(v * 100)):03d}"

# Default picker rule used by pick_top_variants_per_bvariant and recorded in
# picks.json for every step's finalize pass.
_DEFAULT_PICKER_RULE = (
    "per-scene outlier gate (err <= 0 OR err <= median+25%, blob <= 0 OR "
    "blob <= median+50%) + hard rejects: any scene err > 1%, blob > 25%, "
    "or mean rays > 50%. (err cap is absolute: signed mean-err can go "
    "negative from denoising while concentrated artifacts exist; >1% "
    "means the cache demonstrably makes a scene worse.) Rank survivors "
    "by balance score = rays_mean + 1.5×max(scene_blob) + "
    "2.0×max(scene_err); noise informational."
)

# Y-axis limits for the step overview plots (shared across all steps so
# cross-step visual comparison stays consistent).
RAYS_YLIM        = (0, 105)
ERROR_DELTA_YLIM = (-100, 200)
NOISE_DELTA_YLIM = (-30, 10)
ERROR_ABS_YLIM   = (0, 200)
NOISE_ABS_YLIM   = (0, 100)

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
               "mean_level", "min_level", "max_level",
               "error_delta_pct", "error_delta_min_pct", "error_delta_max_pct",
               "error_delta_blob_pct", "error_delta_blob_sum_pct",
               # Cluster-blob: sustained-artifact discriminator. Max err
               # where every pixel in a 5x5 window also exceeds it. Single
               # firefly outliers vanish; localized clusters dominate.
               # Used as the picker's hard-reject signal.
               "error_artifact_pct",
               # Vanilla baseline at the same SPP — absolute err vs GT, for
               # side-by-side comparison (not subtracted from cache numbers).
               "vanilla_err_pct", "vanilla_err_blob_pct",
               "vanilla_err_artifact_pct",
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
                     noise_delta_blob_pct=None, mean_level=None,
                     error_delta_blob_sum_pct=None,
                     min_level=None, max_level=None,
                     vanilla_err_pct=None, vanilla_err_blob_pct=None,
                     error_artifact_pct=None,
                     vanilla_err_artifact_pct=None):
    """Upsert one row keyed by experiment identity (scene + config).
    key = f"{scene}_{prefix.rstrip('_')}" — encodes all run parameters.
    Re-run of the same experiment overwrites its row; different configs coexist.

    error_delta_pct: signed mean-% (err_vis_gt − err_van_gt) / err_van_gt × 100 (OkLab, vs GT).
    error_delta_{min,max}_pct: per-pixel min/max of the same signed delta, same normalization.
    error_delta_blob_pct: signed worst-blob value (Gaussian-blurred delta, sign preserved).
    noise_delta_pct: signed mean-% (noise_vis − noise_van) / noise_van × 100 (bilateral screen noise).
    noise_delta_{min,max}_pct: per-pixel min/max of the same signed delta.
    noise_delta_blob_pct: worst-blob of bilateral noise delta — flags fireflies
        (localized bright pixels not caught by mean-noise metric).
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
        "mean_level":      f"{mean_level:.3f}" if mean_level is not None else "",
        "min_level":       f"{min_level:.3f}"  if min_level  is not None else "",
        "max_level":       f"{max_level:.3f}"  if max_level  is not None else "",
        "error_delta_pct":      f"{error_delta_pct:.4f}"      if error_delta_pct      is not None else "",
        "error_delta_min_pct":  f"{error_delta_min_pct:.4f}"  if error_delta_min_pct  is not None else "",
        "error_delta_max_pct":  f"{error_delta_max_pct:.4f}"  if error_delta_max_pct  is not None else "",
        "error_delta_blob_pct": f"{error_delta_blob_pct:.4f}" if error_delta_blob_pct is not None else "",
        "error_delta_blob_sum_pct": f"{error_delta_blob_sum_pct:.4f}" if error_delta_blob_sum_pct is not None else "",
        "error_artifact_pct":   f"{error_artifact_pct:.4f}" if error_artifact_pct is not None else "",
        "vanilla_err_pct":      f"{vanilla_err_pct:.4f}"      if vanilla_err_pct      is not None else "",
        "vanilla_err_blob_pct": f"{vanilla_err_blob_pct:.4f}" if vanilla_err_blob_pct is not None else "",
        "vanilla_err_artifact_pct": f"{vanilla_err_artifact_pct:.4f}" if vanilla_err_artifact_pct is not None else "",
        "noise_delta_pct":      f"{noise_delta_pct:.4f}"      if noise_delta_pct      is not None else "",
        "noise_delta_min_pct":  f"{noise_delta_min_pct:.4f}"  if noise_delta_min_pct  is not None else "",
        "noise_delta_max_pct":  f"{noise_delta_max_pct:.4f}"  if noise_delta_max_pct  is not None else "",
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
     ("r1c3_accum_error",      "error Δ μ{error_delta_pct:+.1f}% blob{error_delta_blob_pct:+.1f}% sum{error_delta_blob_sum_pct:+.2f}"),
     ("r1c9_accum_noise",      "noise Δ μ{noise_delta_pct:+.1f}%")],
    [("r2c1_frame_level",      "level [{min_level:.0f}..{max_level:.0f}] μ{mean_level:.0f}"),
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
    out = _out(plate_dir, "plate", f"{_scene_prefix(scene_name)}{scene_name}_{prefix}")
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
ERROR_DELTA_YLIM  = (-100, 200)
NOISE_DELTA_YLIM  = (-30, 10)
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
    "02": "Addressing sweep: 4 B-side variants (single level)",
    "03": "Per-axis quant sweep: qA × qB / qA × qD / qA × qD × qd (single level)",
    "04": "SPP convergence for step-03 top-3 per B-variant (x1/x4/x16 SPP)",
    "05": "Quant × threshold sweep on pos__pos (single level)",
    "06": "varThreshold sweep (single level)",
    "09": "Jitter sweep (single level)",
    "10": "Quant × threshold sweep on pos__pos (multi-level)",
    "11": "varThreshold sweep at ct4 fp0 on step-10 carry (multi-level)",
    "14": "Combined sweep: 2 quant × 2 threshold × 3 footprint (multi-level)",
}

def _step_title(step_name):
    return _STEP_TITLES.get(step_name, "")


def _plot_metric(rows, step_name, metric_key, ylabel, title_suffix, out_suffix,
                 ylim=None, zero_line=False, include_neg=False,
                 whisker_blob_key=None,
                 symlog_linthresh=None,
                 ax=None, save=True, prev_winner=None,
                 winners=None, inherited=None, ref_rows=None, ref_label=None,
                 rank_reference_variants=None):
    """Scatter: one metric — scene groups on x-axis, (variant×spp) series.

    Visual encoding (new-schema, quant steps):
      Hue         = qA rank (turbo 0.05..0.95)
      Saturation  = qB OR qD rank (0.50..1.00, desaturated toward gray)
      Alpha       = qd rank OR threshold rank (0.40..1.00) — step-05 case
                    (no qd) repurposes alpha for threshold
      Marker      = B-side core (pos / dir_dist1 / dir_dist) or qA rank in
                    jitter-step multi-quant mode
      Size        = SPP (x1 small, x4/x16 larger)

    Jitter steps (jf_n > 0) override hue/sat to use jf/jc axes.

    Legacy-schema fallback (no qA/jf tokens): B-core complexity rank + viridis
    ramp indexed on the step's main-topic hue key.

    Halos:
      Red circle (size=260) = variant in `winners` set (carried forward).
      Red horizontal tick over whisker endpoint = winner also has a whisker.
      Red star (large) = reference rows from another step (ref_rows param).

    metric_key: row key to plot. Rows where row[metric_key] is None are skipped.
    include_neg: if False, also skip rows where value < 0.
    whisker_blob_key: optional row key holding the signed worst-correlated-blob
                      value (Gaussian-blurred peak). Drawn as a whisker + tick.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba
    import numpy as np

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
    # Rank maps (qA/qB/qD/…) drive hue & saturation. Callers plotting a
    # subset of the full step (per-B-variant splits, top-3 comparison) pass
    # the full step's variants here so the same numeric value always maps
    # to the same hue across subset plots — otherwise qA024 in pos (rank 2/4)
    # lands a different hue than qA024 in dir_dist-filtered (rank 2/3).
    rank_variants = list(rank_reference_variants) if rank_reference_variants else variants
    spps     = sorted(set(r["spp"]     for r in rows if r["spp"] is not None))
    if not spps:
        spps = [1]

    _B = {"pos1":       ("o", 0),
          "pos":        ("o", 2),
          "dir1_dist1": ("D", 1),
          "dir_dist1":  ("v", 3),
          "dir_dist":   ("v", 4)}
    _C_NORM = ["#ffbb78", "#ff7f0e", "#e05c1a", "#a03010", "#802010", "#601808"]

    def _parse(vname):
        """Split variant name into (A-side, B-core, latest_tag).
        The latest tag is parts[-1] — step N inherits the step-(N-1) winner
        as parts[2] and layers its own sweep tag as parts[3+]. Using parts[-1]
        picks up the step's own topic axis.
        Examples:
          pos_norm__dir_dist1                            → ("pos_norm", "dir_dist1", None)
          pos_norm__dir_dist1__qa012                     → ("pos_norm", "dir_dist1", "qa012")
          pos_norm__pos__qa012__th4_fpOff                → ("pos_norm", "pos", "th4_fpOff")
          pos_norm__pos__qa012__fpOff_th4                → ("pos_norm", "pos", "fpOff_th4")
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

    def _scale_val(s):
        if s.startswith("0") and len(s) > 1:
            try: return float("0." + s[1:])
            except ValueError: return 99.0
        try: return float(s)
        except ValueError: return 99.0

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

    def _is_q_token(t):
        """True for qa<digits> / qb<digits> quant tokens."""
        return (t is not None and len(t) > 2 and t[0] == "q" and t[1] in "ab"
                and t[2:].isdigit())

    def _is_ct_token(t):
        """True for ct<digits> tokens (actual bootThreshold sample-count value).
        `ct` = "count" — disambiguates from varThreshold / matureThreshold."""
        return (t is not None and t.startswith("ct")
                and len(t) > 2 and t[2:].isdigit())

    def _q_val(t):
        return _scale_val(t[2:]) if _is_q_token(t) else None

    def _ct_val(t):
        return int(t[2:]) if _is_ct_token(t) else None

    def _axis_token(vname, prefix):
        plen = len(prefix)
        for p in vname.split("__"):
            for t in p.split("_"):
                if t.startswith(prefix) and len(t) > plen:
                    suffix = t[plen:]
                    if suffix.isdigit():
                        return t
        return None

    # qa/qb lowercase (step 14 naming) treated as qA/qB. Other axes follow
    # their original case.
    def _qA_of(v): return _axis_token(v, "qA") or _axis_token(v, "qa")
    def _qB_of(v): return _axis_token(v, "qB") or _axis_token(v, "qb")
    def _qD_of(v): return _axis_token(v, "qD")
    def _qd_of(v): return _axis_token(v, "qd")
    def _jf_of(v): return _axis_token(v, "jf")
    def _jc_of(v): return _axis_token(v, "jc")
    def _vt_of(v): return _axis_token(v, "vt")
    def _se_of(v): return _axis_token(v, "se")
    def _hc_of(v): return _axis_token(v, "hc")
    def _ad_of(v): return _axis_token(v, "ad")

    def _axis_val(tok, prefix, scale_factor):
        """Numeric value from an axis token (e.g. 'qA012' → 0.12 with factor 0.01;
        'qD15' → 15 with factor 1; 'jf1' → 1 with factor 1). Special case:
        'vt0' → 0.0001 (semantic "trace on any var > 0 modulo eps") — a bare
        vt0 would otherwise collapse to 0.0 and shader-compare as never-trust,
        which is not what the sweep is probing."""
        if tok is None:
            return None
        s = tok[len(prefix):]
        if prefix == "vt" and s == "0":
            return 0.0001
        try:
            return int(s) * scale_factor
        except ValueError:
            return None

    def _build_rank(values):
        """Per-axis rank map: each unique value → position in [0, N-1]."""
        uniq = sorted({v for v in values if v is not None})
        return {v: i for i, v in enumerate(uniq)}, len(uniq)

    def _hue_key(tag):
        """Strip fp* tokens (scale encoded in fill alpha, not hue) and return
        the main topic. If nothing but fp tokens remain (pure scale sweep,
        e.g. step 07), return None so hue falls back to the B-core color
        (uniform across the sweep) and the fp scale is communicated solely
        by fill transparency — monotonic, single-hue ramp in the legend.
          qa012             → qa012
          th2_fpOff         → th2
          th1_fp05          → th1
          fp1               → None    (scale-only sweep → alpha encodes it)
        """
        if tag is None:
            return None
        toks   = tag.split("_")
        non_fp = [t for t in toks if not _is_fp_token(t)]
        if non_fp:
            return "_".join(non_fp)
        return None

    def _tag_sort_key(k):
        toks = k.split("_")
        th_v = next((_ct_val(t) for t in toks if _is_ct_token(t)), None)
        q_v  = next((_q_val(t)  for t in toks if _is_q_token(t)),  None)
        scale = _fp_scale_val(k)
        th_rank = th_v if th_v is not None else 99
        q_rank  = q_v  if q_v  is not None else 99
        s_rank  = scale if scale is not None else -1.0
        return (th_rank, q_rank, s_rank, k)
    _all_tags = sorted({_parse(v)[2] for v in rank_variants if _parse(v)[2] is not None},
                       key=_tag_sort_key)

    def _alpha(vname):
        """With hue now encoding the main-topic tag, the alpha gradient is
        retired — every point is fully opaque."""
        return 1.0

    def _ramp_color(i, n):
        if n <= 1:
            return plt.cm.viridis(0.5)
        return plt.cm.viridis(0.15 + 0.70 * (i / (n - 1)))
    _TAG_PALETTE = plt.cm.tab10.colors
    _MARKER_CYCLE = ["v", "o", "^", "s", "D", "P", "X"]

    def _quant_of(vname):
        for p in vname.split("__"):
            for t in p.split("_"):
                if _is_q_token(t): return t
        return None

    def _ct_of(vname):
        for p in vname.split("__"):
            for t in p.split("_"):
                if _is_ct_token(t): return t
        return None

    def _fp_of(vname):
        """Return fp tag matching fp<digits>, fpOff, fpOn, or fpS<digits>."""
        for p in vname.split("__"):
            for t in p.split("_"):
                if t in ("fpOff", "fpOn"):
                    return t
                if t.startswith("fp") and len(t) > 2:
                    tail = t[3:] if t.startswith("fpS") else t[2:]
                    if tail.isdigit():
                        return t
        return None

    # Per-axis rank maps over the variant set.
    _qA_rank, _qA_n = _build_rank(_axis_val(_qA_of(v), "qA", 0.01) for v in rank_variants)
    _qB_rank, _qB_n = _build_rank(_axis_val(_qB_of(v), "qB", 0.01) for v in rank_variants)
    _qD_rank, _qD_n = _build_rank(_axis_val(_qD_of(v), "qD", 1.0)  for v in rank_variants)
    _qd_rank, _qd_n = _build_rank(_axis_val(_qd_of(v), "qd", 0.01) for v in rank_variants)
    _jf_rank, _jf_n = _build_rank(_axis_val(_jf_of(v), "jf", 0.1)  for v in rank_variants)
    _jc_rank, _jc_n = _build_rank(_axis_val(_jc_of(v), "jc", 0.1)  for v in rank_variants)
    _thr_rank, _thr_n = _build_rank(_ct_val(_ct_of(v)) for v in rank_variants)
    _vt_rank, _vt_n = _build_rank(_axis_val(_vt_of(v), "vt", 0.01) for v in rank_variants)
    _fp_rank, _fp_n = _build_rank(_fp_scale_val(_fp_of(v)) for v in rank_variants)
    _se_rank, _se_n = _build_rank(_axis_val(_se_of(v), "se", 0.01) for v in rank_variants)
    _hc_rank, _hc_n = _build_rank(_axis_val(_hc_of(v), "hc", 1.0)  for v in rank_variants)
    _ad_rank, _ad_n = _build_rank(_axis_val(_ad_of(v), "ad", 0.01) for v in rank_variants)
    _new_schema = _qA_n > 0 or _jf_n > 0 or _se_n > 0

    # Dynamic hue/sat axis selection — pick the most-varying axis for hue,
    # second-most for sat. Keeps every variant visually distinct even when
    # the "default" qA axis is degenerate (step 05 → hue=ct; step 06 → hue=vt).
    # jitter axes are excluded because the jitter branch has its own encoding.
    # fp is consumed by marker-shape (not hue/sat) so it's not listed here.
    _HUE_CANDIDATES = [
        ("qA", _qA_n, _qA_rank, lambda v: _axis_val(_qA_of(v), "qA", 0.01)),
        ("ct", _thr_n, _thr_rank, lambda v: _ct_val(_ct_of(v))),
        ("vt", _vt_n, _vt_rank, lambda v: _axis_val(_vt_of(v), "vt", 0.01)),
        ("se", _se_n, _se_rank, lambda v: _axis_val(_se_of(v), "se", 0.01)),
        ("hc", _hc_n, _hc_rank, lambda v: _axis_val(_hc_of(v), "hc", 1.0)),
        ("ad", _ad_n, _ad_rank, lambda v: _axis_val(_ad_of(v), "ad", 0.01)),
        ("qB", _qB_n, _qB_rank, lambda v: _axis_val(_qB_of(v), "qB", 0.01)),
        ("qD", _qD_n, _qD_rank, lambda v: _axis_val(_qD_of(v), "qD", 1.0)),
    ]
    _HUE_CAND_SORTED = sorted([c for c in _HUE_CANDIDATES if c[1] >= 2],
                               key=lambda c: -c[1])
    _HUE_AXIS = _HUE_CAND_SORTED[0] if _HUE_CAND_SORTED else None
    _SAT_AXIS = _HUE_CAND_SORTED[1] if len(_HUE_CAND_SORTED) >= 2 else None
    _HUE_CONSUMED = {c[0] for c in (_HUE_AXIS, _SAT_AXIS) if c is not None}

    # Marker-shape axis. When multiple fp values are present (step 11-style
    # triple sweep vt × ct × fp), map fp rank to a marker-shape cycle so
    # every combination is visually distinct without burning an alpha axis.
    _FP_MARKER_CYCLE = ["o", "^", "s", "D", "P", "v", "X"]
    _FP_MARKER = None
    if _fp_n >= 2:
        _fp_sorted = sorted(_fp_rank.keys())
        _FP_MARKER = {v: _FP_MARKER_CYCLE[i % len(_FP_MARKER_CYCLE)]
                      for i, v in enumerate(_fp_sorted)}

    _quants_in_set  = {_quant_of(v)  for v in rank_variants} - {None}
    _thresh_in_set  = {_ct_of(v) for v in rank_variants} - {None}
    _swap_encoding  = len(_quants_in_set) > 1 and len(_thresh_in_set) > 1
    _thresh_sorted  = sorted(_thresh_in_set, key=lambda t: _ct_val(t) or 0)
    _THRESH_MARKERS = {t: _MARKER_CYCLE[i % len(_MARKER_CYCLE)]
                       for i, t in enumerate(_thresh_sorted)}

    def _hue_override(vname):
        """Override the hue key when quant-threshold swap is active."""
        if _swap_encoding:
            return _quant_of(vname)
        return _hue_key(_parse(vname)[2])

    _hue_keys = sorted({_hue_override(v) for v in rank_variants
                        if _hue_override(v) is not None},
                       key=_tag_sort_key)

    def _desaturate(rgba, sat_frac):
        """Blend rgba toward perceptual gray. sat_frac=1 keeps original;
        sat_frac=0 is fully gray. Uses Rec.709 luma."""
        r, g, b, a = rgba
        gray = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return (gray + (r - gray) * sat_frac,
                gray + (g - gray) * sat_frac,
                gray + (b - gray) * sat_frac,
                a)

    def _axis_frac(rank, n, lo=0.0, hi=1.0):
        """Map rank ∈ [0, n-1] to fraction in [lo, hi]. Single-value axis → hi."""
        if n <= 1:
            return hi
        return lo + (hi - lo) * (rank / (n - 1))

    def _style(vname):
        a, b_core, tag = _parse(vname)
        if a is None:
            return "o", "#888888"
        marker, rank = _B.get(b_core, ("o", 0))

        if _new_schema:
            # Jitter step: hue = jf, sat = jc. Multi-quant jitter uses marker
            # shape to distinguish qA flavors (step 09 pattern).
            if _jf_n > 0:
                jf_v = _axis_val(_jf_of(vname), "jf", 0.1)
                jc_v = _axis_val(_jc_of(vname), "jc", 0.1)
                # viridis (perceptually uniform, no rainbow) reads better than
                # turbo for the 3×3 jf×jc grid. Narrower hue band (0.15–0.90)
                # avoids the darkest/lightest extremes that hurt legibility.
                hue_frac = _axis_frac(_jf_rank.get(jf_v, 0), max(_jf_n, 1), 0.15, 0.90)
                sat_frac = _axis_frac(_jc_rank.get(jc_v, 0), max(_jc_n, 1), 0.35, 1.00)
                if _qA_n > 1:
                    qA_v = _axis_val(_qA_of(vname), "qA", 0.01)
                    _JITTER_QUANT_MARKERS = ["o", "s", "D", "^", "v"]
                    marker = _JITTER_QUANT_MARKERS[_qA_rank.get(qA_v, 0)
                                                   % len(_JITTER_QUANT_MARKERS)]
                base = plt.cm.viridis(hue_frac)
                return marker, _desaturate(base, sat_frac)

            # Quant / threshold / varThresh step: dynamic axis selection.
            # Hue = most-varying axis, sat = second-most. When qA is degenerate
            # (step 05 pos-only at one quant, step 06 vt-only), the most-varying
            # axis promotes to hue so variants stay distinguishable.
            if _HUE_AXIS is not None:
                _, hue_n, hue_rank, hue_fn = _HUE_AXIS
                hv = hue_fn(vname)
                if hv is not None and hv in hue_rank:
                    hue_frac = _axis_frac(hue_rank[hv], max(hue_n, 1), 0.05, 0.95)
                else:
                    hue_frac = 0.5
            else:
                hue_frac = 0.5
            if _SAT_AXIS is not None:
                _, sat_n, sat_rank, sat_fn = _SAT_AXIS
                sv = sat_fn(vname)
                if sv is not None and sv in sat_rank:
                    sat_frac = _axis_frac(sat_rank[sv], sat_n, 0.50, 1.00)
                else:
                    sat_frac = 1.0
            else:
                sat_frac = 1.0
            # Marker shape driven by fp rank when fp axis is present.
            if _FP_MARKER is not None:
                fp_v = _fp_scale_val(_fp_of(vname))
                if fp_v is not None and fp_v in _FP_MARKER:
                    marker = _FP_MARKER[fp_v]
            base = plt.cm.turbo(hue_frac)
            return marker, _desaturate(base, sat_frac)

        # Legacy schema path (multi-level steps 10+ retain old tag style).
        if _swap_encoding:
            th = _ct_of(vname)
            if th is not None:
                marker = _THRESH_MARKERS[th]
        hue = _hue_override(vname)
        if hue is not None and hue in _hue_keys:
            color = _ramp_color(_hue_keys.index(hue), len(_hue_keys))
        else:
            color = _C_NORM[rank] if rank < len(_C_NORM) else _TAG_PALETTE[rank % len(_TAG_PALETTE)]
        return marker, color

    def _fp_alpha(vname):
        """Face-fill alpha. Encoding order (first match wins):
          1. qd (distB) rank — new schema, pos__dir_dist variants
          2. Legacy fp<N> / fpOn / fpOff token — pre-refactor tags (steps 10+)
          3. Threshold rank when qd is absent but threshold varies — step 05 case
          4. B-core ends in '1' (collapsed sibling) and no tag → hollow
          5. Otherwise 1.0 (solid)
        """
        _, b_core, tag = _parse(vname)
        if _qd_n > 0:
            qd_v = _axis_val(_qd_of(vname), "qd", 0.01)
            if qd_v is not None:
                return _axis_frac(_qd_rank[qd_v], _qd_n, 0.40, 1.00)
            return 1.0
        scale = _fp_scale_val(tag)
        if scale is not None:
            return max(0.0, min(1.0, scale))
        if _new_schema and _thr_n > 1 and "th" not in _HUE_CONSUMED:
            th_tok = _ct_of(vname)
            th_v = _ct_val(th_tok) if th_tok else None
            if th_v is not None:
                return _axis_frac(_thr_rank[th_v], _thr_n, 0.40, 1.00)
        if b_core and b_core.endswith("1"):
            return 0.0
        return 1.0

    def _size_for_spp(spp):
        """SPP → marker size. Small for x1, growing with SPP."""
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

    def _level_of(vname):
        """Extract numLevels from an L<N> token (e.g. 'L4', 'L16'). None if absent."""
        for p in vname.split("__"):
            for t in p.split("_"):
                if t.startswith("L") and len(t) > 1 and t[1:].isdigit():
                    return int(t[1:])
        return None

    def _sort_key(vname):
        a, b_core, tag = _parse(vname)
        if a is None:
            return (99, 99, 99, vname)
        rank = _B.get(b_core, ("o", 99))[1]
        tag_rank = _all_tags.index(tag) if tag in _all_tags else 99
        level = _level_of(vname)
        level_rank = level if level is not None else -1
        return (level_rank, rank, tag_rank, vname)

    def _valid(v):
        if v is None: return False
        if include_neg: return True
        return v >= 0

    def _row_key(r):
        return (r["variant"], r["spp"],
                int(r.get("warmup_first") or 0),
                int(r.get("warmup_run")   or 0),
                int(r.get("subframe_n")   or 1))
    series_keys = sorted({_row_key(r) for r in rows},
                         key=lambda k: (_sort_key(k[0]), k[1], k[4], k[2], k[3]))

    # Step 01 case: single variant, multiple (sn, warmup) configs.
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
    all_x   = n_sc + 0.4

    n_series = len(series_keys)
    spread   = 0.80
    offsets  = np.linspace(-spread / 2, spread / 2, n_series) if n_series > 1 else [0.0]

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(max(9, (n_sc + 2) * 4.0), 5))
    else:
        fig = ax.figure

    legend_handles = []
    any_point = False
    has_whiskers = whisker_blob_key is not None

    def _matches_any(vname_, patterns):
        if not patterns:
            return False
        for p in patterns:
            if vname_ == p or vname_.startswith(p):
                return True
        return False

    for series_idx, key in enumerate(series_keys):
        vname, spp, w1, wr, sn = key
        marker, color = _style(vname)
        alpha = _alpha(vname)
        # Step 01 subframe/warmup special case: encode subframe N via marker,
        # warmup position via viridis ramp. N=1 = oversized crimson star.
        if _subframe_step and not _hue_keys:
            peers = sorted({(k[2], k[3]) for k in series_keys
                            if k[0] == vname and k[4] == sn})
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
                color  = "#d62728"
        face_rgba = _darken_for_spp(color, spp)
        fill_alpha = _fp_alpha(vname)
        fc = "none" if fill_alpha <= 0.01 else (face_rgba[0], face_rgba[1], face_rgba[2], fill_alpha)
        size   = _size_for_spp(spp)
        if _subframe_step and not _hue_keys and sn == 1:
            size = size + 40
            fc   = face_rgba
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
                    blob = max(0.0, float(blob))
                    if blob > 0:
                        whiskers.append((x, y, blob))

        # "All" column: weighted mean across scenes; whisker tip = max blob across ALL scenes.
        scene_means, scene_weights_list, scene_blobs = [], [], []
        for s in scenes:
            matching = [r for r in rows
                        if _row_key(r) == key and r["scene"] == s and _valid(r.get(metric_key))]
            if not matching:
                continue
            scene_means.append(float(np.mean([r[metric_key] for r in matching])))
            scene_weights_list.append(_scene_weight(s))
            if has_whiskers:
                blobs = [max(0.0, float(r[whisker_blob_key]))
                         for r in matching if r.get(whisker_blob_key) is not None]
                blobs = [b for b in blobs if b > 0]
                if blobs:
                    scene_blobs.append(max(blobs))
        if scene_means:
            x_all = all_x + offsets[series_idx]
            ws = sum(scene_weights_list)
            mean_all = float(sum(m * w for m, w in zip(scene_means, scene_weights_list)) / ws)                         if ws > 0 else float(np.mean(scene_means))
            pts.append((x_all, mean_all))
            if has_whiskers and scene_blobs:
                whiskers.append((x_all, mean_all, max(scene_blobs)))

        if not pts:
            continue
        tick_half = 0.045 + 0.0008 * size
        is_winner = _matches_any(vname, winners) if winners else False
        for (wx, wlo, whi) in whiskers:
            ax.vlines(wx, wlo, whi, color=color, alpha=0.5 * alpha, linewidth=1.2, zorder=2)
            ax.hlines(whi, wx - tick_half, wx + tick_half,
                      color=color, alpha=1.0 * alpha, linewidth=2.6, zorder=3)
            if is_winner:
                ax.hlines(whi, wx - tick_half * 1.2, wx + tick_half * 1.2,
                          color="#d62728", alpha=1.0, linewidth=1.0, zorder=5)
        xs, ys = zip(*pts)
        h = ax.scatter(xs, ys, label=label, marker=marker,
                       edgecolors=face_rgba, facecolors=fc,
                       linewidths=1.2, s=size, zorder=3)
        legend_handles.append(h)
        any_point = True
        # Red winner halo (fixed size, thin outline so SPP markers stay visible).
        _HALO_SIZE = 260
        if _matches_any(vname, winners):
            ax.scatter(xs, ys, marker="o",
                       edgecolors="#d62728", facecolors="none",
                       linewidths=0.9, s=_HALO_SIZE, zorder=4)

    if not any_point:
        if own_fig:
            plt.close(fig)
        return None

    # Red-star reference overlay.
    if ref_rows:
        ref_by_spp = {}
        for rr in ref_rows:
            if not _valid(rr.get(metric_key)):
                continue
            ref_by_spp.setdefault(rr["spp"], []).append(rr)
        ref_handle = None
        for spp, rrs in ref_by_spp.items():
            size = _size_for_spp(spp) + 50
            xs_r, ys_r = [], []
            for rr in rrs:
                if rr["scene"] in scene_x:
                    xs_r.append(scene_x[rr["scene"]])
                    ys_r.append(rr[metric_key])
            vals = [(rr[metric_key], _scene_weight(rr["scene"])) for rr in rrs]
            ws = sum(w for _, w in vals)
            if ws > 0:
                xs_r.append(all_x)
                ys_r.append(sum(v * w for v, w in vals) / ws)
            if xs_r:
                h = ax.scatter(xs_r, ys_r, marker="*",
                               edgecolors="#d62728", facecolors="#d62728",
                               linewidths=0.6, s=size, zorder=5,
                               label=(ref_label or "single-level ref") + f" x{spp}")
                if ref_handle is None:
                    ref_handle = h
                    legend_handles.insert(0, h)
                else:
                    legend_handles.insert(1, h)
            if has_whiskers:
                ref_whiskers = []
                ref_scene_blobs = []
                for rr in rrs:
                    if rr["scene"] not in scene_x:
                        continue
                    blob = rr.get(whisker_blob_key)
                    if blob is None:
                        continue
                    blob = max(0.0, float(blob))
                    if blob <= 0:
                        continue
                    ref_whiskers.append((scene_x[rr["scene"]], rr[metric_key], blob))
                    ref_scene_blobs.append(blob)
                if ref_scene_blobs and ws > 0:
                    mean_all_y = sum(v * w for v, w in vals) / ws
                    ref_whiskers.append((all_x, mean_all_y, max(ref_scene_blobs)))
                ref_tick = 0.045 + 0.0008 * size
                for (wx, wlo, whi) in ref_whiskers:
                    ax.vlines(wx, wlo, whi, color="#d62728", alpha=0.55,
                              linewidth=1.2, zorder=4)
                    ax.hlines(whi, wx - ref_tick, wx + ref_tick,
                              color="#d62728", alpha=1.0, linewidth=1.8,
                              zorder=5)

    ax.set_xticks(list(range(n_sc)) + [all_x])
    ax.set_xticklabels([s.replace("CornellBox_", "") for s in scenes] + ["All"],
                       rotation=20, ha="right", fontsize=9)
    ax.axvline(x=n_sc - 0.5, color="#bbbbbb", linestyle="--", linewidth=0.8, zorder=1)

    if zero_line:
        ax.axhline(y=0, color="#666666", linestyle="-", linewidth=0.8, zorder=2)

    ax.set_ylabel(ylabel)
    ax.set_title(title_suffix, fontsize=10, loc="left")
    if own_fig:
        step_main = _step_title(step_name)
        suptitle = f"Step {step_name}" + (f" — {step_main}" if step_main else "")
        fig.suptitle(suptitle, fontsize=11)
        _add_adaptive_legend(ax, legend_handles, figlevel=False)
    if symlog_linthresh is not None:
        ax.set_yscale("symlog", linthresh=symlog_linthresh, linscale=0.5)
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
        return legend_handles

    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"overview_{out_suffix}_{step_name}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[overview] {out}")
    return out


def plot_overviews(step_name, prev_winner=None, carried_winners=None,
                    inherited_winners=None, ref_step=None, ref_variant=None,
                    ref_label=None, variant_filter=None):
    """Generates three overview scatter plots per step:
      overview_rays_<step>.png   — rays traced %
      overview_error_<step>.png  — signed GT-error Δ vs vanilla %
      overview_noise_<step>.png  — absolute mean OkLab distance to GT, % of viridis max

    variant_filter: optional callable(variant_name) -> bool. When set,
    excludes matching-False rows from the plot (CSV unchanged). Used by
    step 11 to hide fp>0 rows from the dense 48-variant sweep.

    Returns list of paths (may contain None entries for metrics with no data).
    """
    rows = _load_step_rows(step_name)
    if not rows:
        print(f"[overview] No data in step {step_name}")
        return None
    # Rank-reference = full row set so hue/sat maps stay consistent with
    # unfiltered plots; filtering only affects which points are drawn.
    rank_reference_variants = sorted({r["variant"] for r in rows}) if variant_filter else None
    if variant_filter is not None:
        rows = [r for r in rows if variant_filter(r["variant"])]

    # Red-circle overlay: carried forward to next step. Resolution order:
    #   1. explicit carried_winners argument (highest priority)
    #   2. picks.json for this step (authoritative record of manual carries
    #      and picker overrides — see step 05's th2 override vs auto-picker's
    #      th1 top-1)
    #   3. live auto-picker (fallback when no picks.json exists yet)
    if carried_winners is not None:
        winners = set(carried_winners)
    else:
        import json
        picks_path = os.path.join("captures", "ladder", step_name, "picks.json")
        if os.path.exists(picks_path):
            with open(picks_path) as f:
                meta = json.load(f)
            carried = meta.get("carried") or {}
            winners = {n for vs in carried.values() for n in vs}
        else:
            picks = pick_top_variants_per_bvariant(step_name, n_top=1, spp=1)
            winners = {v for vs in picks.values() for v in vs}
    inherited = set(inherited_winners) if inherited_winners else None
    ref_rows = _resolve_ref_rows(ref_step, ref_variant)

    out_rays  = _plot_metric(rows, step_name, "rays_traced_pct",
                             ylabel="rays traced %", title_suffix="rays traced",
                             out_suffix="rays", ylim=RAYS_YLIM, prev_winner=prev_winner,
                             winners=winners, inherited=inherited,
                             ref_rows=ref_rows, ref_label=ref_label,
                             rank_reference_variants=rank_reference_variants)
    out_err   = _plot_metric(rows, step_name, "error_delta_pct",
                             ylabel="error Δ % (symlog)", title_suffix="error Δ (whisker: max blob)",
                             out_suffix="error", zero_line=True, include_neg=True,
                             whisker_blob_key="error_delta_blob_pct",
                             ylim=ERROR_DELTA_YLIM,
                             symlog_linthresh=3.0, prev_winner=prev_winner,
                             winners=winners, inherited=inherited,
                             ref_rows=ref_rows, ref_label=ref_label,
                             rank_reference_variants=rank_reference_variants)
    out_noise = _plot_metric(rows, step_name, "noise_delta_pct",
                             ylabel="noise Δ % (symlog)", title_suffix="noise Δ",
                             out_suffix="noise", zero_line=True, include_neg=True,
                             ylim=NOISE_DELTA_YLIM,
                             symlog_linthresh=1.0, prev_winner=prev_winner,
                             winners=winners, inherited=inherited,
                             ref_rows=ref_rows, ref_label=ref_label,
                             rank_reference_variants=rank_reference_variants)
    out_combined = _plot_combined(rows, step_name, prev_winner=prev_winner,
                                   rank_reference_variants=rank_reference_variants,
                                   winners=winners, inherited=inherited,
                                   ref_rows=ref_rows, ref_label=ref_label)
    return [out_rays, out_err, out_noise, out_combined]


def _plot_combined(rows, step_name, prev_winner=None, out_suffix="", title_suffix="",
                    winners=None, inherited=None, ref_rows=None, ref_label=None,
                    rank_reference_variants=None):
    """3-panel stacked plot sharing x-axis: rays (top), error Δ (mid), noise Δ (bottom).
    Each panel uses _plot_metric with whiskers on the signed metrics. Single legend
    on the right applies to all three panels.

    out_suffix: appended to output filename (e.g. "_pos") for per-subset plots.
    title_suffix: appended to the figure suptitle after the step title.
    winners / inherited / ref_rows / ref_label: forwarded to each _plot_metric
    call so halos + red-star reference render identically across panels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenes = sorted(set(r["scene"] for r in rows))
    n_sc = len(scenes)
    fig, axes = plt.subplots(3, 1,
                             figsize=(max(9, (n_sc + 2) * 4.0), 10),
                             sharex=True,
                             constrained_layout=True)

    _plot_metric(rows, step_name, "rays_traced_pct",
                 ylabel="rays traced %", title_suffix="rays traced",
                 out_suffix="rays", ylim=RAYS_YLIM,
                 ax=axes[0], save=False, winners=winners, inherited=inherited,
                 ref_rows=ref_rows, ref_label=ref_label,
                 rank_reference_variants=rank_reference_variants)
    _plot_metric(rows, step_name, "error_delta_pct",
                 ylabel="error Δ % (symlog)", title_suffix="error Δ (whisker: max blob)",
                 out_suffix="error", zero_line=True, include_neg=True,
                 whisker_blob_key="error_delta_blob_pct",
                 ylim=ERROR_DELTA_YLIM,
                 symlog_linthresh=3.0,
                 ax=axes[1], save=False, winners=winners, inherited=inherited,
                 ref_rows=ref_rows, ref_label=ref_label,
                 rank_reference_variants=rank_reference_variants)
    legend_handles = _plot_metric(rows, step_name, "noise_delta_pct",
                                  ylabel="noise Δ % (symlog)", title_suffix="noise Δ",
                                  out_suffix="noise", zero_line=True, include_neg=True,
                                  ylim=NOISE_DELTA_YLIM,
                                  symlog_linthresh=1.0,
                                  ax=axes[2], save=False, winners=winners, inherited=inherited,
                                  ref_rows=ref_rows, ref_label=ref_label,
                                  rank_reference_variants=rank_reference_variants)

    step_main = _step_title(step_name)
    suptitle = f"Step {step_name}" + (f" — {step_main}" if step_main else "")
    if title_suffix:
        suptitle += f"   |   {title_suffix}"
    # prev_winner intentionally not rendered — inherited base is marked
    # visually (post-.pyc simplification per user feedback).
    fig.suptitle(suptitle, fontsize=11)
    if isinstance(legend_handles, list) and legend_handles:
        _add_adaptive_legend(fig, legend_handles, figlevel=True)

    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    fname = f"overview_summary_{step_name}{out_suffix}.png"
    out = os.path.join(out_dir, fname)
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


def _pick_step_winner_for_plot(step, ladder_root="captures/ladder"):
    """Progression-plot winner selection with a 3-level fallback:
      1. picks.json `carried` field (manual override)
      2. pick_top_variants_per_bvariant auto-picker (hard caps applied)
      3. Lowest weighted-score variant at spp=1 regardless of caps

    Level 3 ensures every step shows a data point on the progression plot
    even when no variant survives the absolute blob/err/rays caps (e.g.
    Sponza-era steps where every variant has blob > 25%).
    """
    import json, csv
    winner = None
    picks_path = os.path.join(ladder_root, step, "picks.json")
    if os.path.exists(picks_path):
        with open(picks_path) as f:
            meta = json.load(f)
        carried = meta.get("carried") or {}
        names = [n for vs in carried.values() for n in vs]
        if names:
            winner = names[0]
    if winner is None:
        picks = pick_top_variants_per_bvariant(step, n_top=1, spp=1)
        names = [v for vs in picks.values() for v in vs]
        if names:
            winner = names[0]
    if winner is None:
        rows_path = _step_csv(step)
        if os.path.exists(rows_path):
            variant_score = {}
            with open(rows_path, newline="") as f:
                for r in csv.DictReader(f):
                    try:
                        row_spp = int(r.get("spp") or 1)
                    except ValueError:
                        row_spp = 1
                    if row_spp != 1:
                        continue
                    v = r.get("variant")
                    rays = float(r.get("rays_traced_pct") or 100.0)
                    err  = float(r.get("error_delta_pct") or 0.0)
                    blob = float(r.get("error_delta_blob_pct") or 0.0)
                    sc = rays + 1.5 * max(blob, 0.0) + 2.0 * max(err, 0.0)
                    variant_score.setdefault(v, []).append(sc)
            if variant_score:
                means = {v: sum(ss) / len(ss) for v, ss in variant_score.items()}
                winner = min(means, key=means.get)
    return winner


def plot_ladder_progress(steps=None, spp=1):
    """Cross-step progression plot: for each step, look up its carried
    winner (picks.json when present, else live auto-pick) and render
    rays / error+blob / noise for that winner across scenes plus a bold
    weighted-"All" line (SCENE_WEIGHTS — 32PL × 3).

    Error panel includes a companion "max blob error" series (dashed
    triangles + dotted whiskers) on the same axis so the err/blob tradeoff
    is visible in one panel. Whiskers per step per scene show the min-to-max
    range across all variants at that step (thin colored stem + horizontal
    tick endline; black stem + bold endline for the All envelope).

    gridspec row heights [1.0, 1.3, 0.6] — error panel slightly taller to
    fit the companion series, noise shorter because its range is narrow.

    steps: optional ordered list of step numbers. Default: every two-digit
    step dir under captures/ladder/ with a stats.csv, excluding the
    WIP-bucket list (11, 14).
    spp: which SPP tier to plot. Default 1; pass 4 for the x4 companion.

    Output: captures/ladder/ladder_progress_x<spp>.png.
    """
    import json, csv, glob
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ladder_root = "captures/ladder"
    # Steps excluded from the progression plot by default. Kept in the ladder
    # root (their CSVs still exist) but not shown here — e.g. WIP multi-level
    # expansions that would distort the per-scene comparison against the
    # single-level spine. Callers can pass `steps=` explicitly to override.
    # Steps 16-17 (skipped/retired) and the archive_post_alignment range
    # (18-29 + 31-52) are excluded from progression plots — measured under
    # earlier broken-cascade or stride-fragmented regimes, not comparable
    # to the current ladder. The new ladder steps 11-15 are included.
    # All step numbers are valid post-archive (steps 11-25+ are the current
    # ladder restart). The previous exclude list dropped pre-archive 11-52
    # which no longer exist on disk.
    _exclude = set()
    if steps is None:
        steps = []
        for p in sorted(glob.glob(os.path.join(ladder_root,
                                                  "[0-9][0-9]", "stats.csv"))):
            step_num = os.path.basename(os.path.dirname(p))
            if step_num in _exclude:
                continue
            steps.append(step_num)
    if not steps:
        print("[progress] No step stats.csv files found.")
        return None

    # series[step] = {scene: {rays, err, blob, noise}}   (winner's per-scene metrics)
    # ranges[step] = {scene: {rays:(lo,hi), ...}}         (min/max across all variants)
    series = {}
    ranges = {}
    winners_label = {}
    for step in steps:
        winner = _pick_step_winner_for_plot(step, ladder_root)
        if winner is None:
            continue
        winners_label[step] = winner
        rows_path = _step_csv(step)
        if not os.path.exists(rows_path):
            continue
        per_scene = {}
        scene_range_buckets = {}
        with open(rows_path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    row_spp = int(r.get("spp") or 1)
                except ValueError:
                    row_spp = 1
                if row_spp != spp:
                    continue
                def _f(k, default=None):
                    v = r.get(k, "")
                    try:
                        return float(v) if v not in ("", None) else default
                    except ValueError:
                        return default
                scene = r["scene"]
                if r["variant"] == winner:
                    per_scene[scene] = {
                        "rays":  _f("rays_traced_pct", 0.0),
                        "err":   _f("error_delta_pct", 0.0),
                        "blob":  _f("error_delta_blob_pct", 0.0),
                        "noise": _f("noise_delta_pct", 0.0),
                    }
                b = scene_range_buckets.setdefault(scene,
                    {"rays": [], "err": [], "blob": [], "noise": []})
                for mk, ck in (("rays", "rays_traced_pct"),
                                ("err", "error_delta_pct"),
                                ("blob", "error_delta_blob_pct"),
                                ("noise", "noise_delta_pct")):
                    v = _f(ck)
                    if v is not None:
                        b[mk].append(v)
        per_range = {s: {mk: (min(vs), max(vs)) if vs else None
                          for mk, vs in b.items()}
                      for s, b in scene_range_buckets.items()}
        if per_scene:
            series[step] = per_scene
            ranges[step] = per_range

    _SCENE_ORDER = [
        "CornellBox_1PointLight", "CornellBox_1AreaLight",
        "CornellBox_3AreaLights", "CornellBox_32PointLights",
    ]
    all_scenes = sorted({s for sc in series.values() for s in sc.keys()},
                         key=lambda s: _SCENE_ORDER.index(s)
                                       if s in _SCENE_ORDER else 99)
    if not all_scenes:
        all_scenes = [os.path.splitext(s)[0] for s in ALL_SCENES]

    # Synthetic step-00 anchor (rays=100, err/noise/blob=0 by definition).
    if "00" in steps and "00" not in series:
        series["00"] = {s: {"rays": 100.0, "err": 0.0, "blob": 0.0,
                             "noise": 0.0} for s in all_scenes}
        winners_label["00"] = "vanilla (baseline)"

    if not series:
        print("[progress] No winner metrics found for any step.")
        return None

    step_keys = [s for s in steps if s in series]
    n_steps = len(step_keys)
    x = list(range(n_steps))

    # 3-panel layout: error gets 1.3× row height (has companion blob series);
    # noise gets 0.6× (narrow range, doesn't need the full height).
    fig, axes = plt.subplots(3, 1, figsize=(max(8, n_steps * 2.0), 9),
                              sharex=True, constrained_layout=True,
                              gridspec_kw={"height_ratios": [1.0, 1.3, 0.6]})
    metric_defs = [
        ("rays",  "rays traced %",   False, None,    None,  RAYS_YLIM,           1.0),
        ("err",   "error Δ %",       True,  "symlog", "blob", ERROR_DELTA_YLIM,   3.0),
        ("noise", "noise Δ %",       True,  "symlog", None,  NOISE_DELTA_YLIM,    1.0),
    ]
    # Dynamic turbo spread: N scenes → N distinct hues across [0.05, 0.95],
    # avoiding the color cycling that happened with the old fixed 4-slot
    # palette once Bistro / Sponza joined the scene list.
    import numpy as _np
    n_sc = max(1, len(all_scenes))
    scene_colors = plt.cm.turbo(_np.linspace(0.05, 0.95, n_sc))
    for ax, (mkey, ylabel, zeroline, yscale, companion_mkey, ylim, lin_thresh) in zip(axes, metric_defs):
        # Per-scene thin lines.
        for i, scene in enumerate(all_scenes):
            ys = [series[s].get(scene, {}).get(mkey) for s in step_keys]
            ax.plot(x, ys, marker="o", linewidth=1.5, markersize=6,
                    color=scene_colors[i], alpha=0.85,
                    label=scene.replace("CornellBox_", ""))
        # Range whiskers per scene: thin colored stem + horizontal tick at max.
        tick_half = 0.12
        for i, scene in enumerate(all_scenes):
            for si, s in enumerate(step_keys):
                rng = ranges.get(s, {}).get(scene, {}).get(mkey)
                if rng is None:
                    continue
                lo, hi = rng
                if hi <= lo:
                    continue
                col = scene_colors[i]
                ax.vlines(si, lo, hi, color=col, alpha=0.5,
                          linewidth=1.2, zorder=2)
                ax.hlines(hi, si - tick_half, si + tick_half,
                          color=col, linewidth=2.4, zorder=3)
        # Weighted "All" line + envelope whisker.
        all_ys = []
        all_whiskers = []
        for si, s in enumerate(step_keys):
            vals, ws = [], []
            for scene, metrics in series[s].items():
                v = metrics.get(mkey)
                if v is None:
                    continue
                vals.append(v)
                ws.append(_scene_weight(scene))
            all_ys.append(sum(v * w for v, w in zip(vals, ws)) / sum(ws)
                          if ws else None)
            lo, hi = float("inf"), float("-inf")
            for scene, scene_ranges in ranges.get(s, {}).items():
                rng = scene_ranges.get(mkey)
                if rng is None:
                    continue
                lo = min(lo, rng[0]); hi = max(hi, rng[1])
            if hi > lo:
                all_whiskers.append((si, lo, hi))
        for (si, lo, hi) in all_whiskers:
            ax.vlines(si, lo, hi, color="#000000", alpha=0.5,
                      linewidth=1.0, zorder=4)
            ax.hlines(hi, si - tick_half, si + tick_half,
                      color="#000000", linewidth=1.8, zorder=5)
        ax.plot(x, all_ys, marker="D", linewidth=2.0, markersize=7,
                color="#000000", zorder=6, label="All (weighted, 32PL×3)")

        # Companion series (blob on error panel): dashed + triangle marker.
        if companion_mkey:
            for i, scene in enumerate(all_scenes):
                ys = [series[s].get(scene, {}).get(companion_mkey) for s in step_keys]
                ax.plot(x, ys, marker="^", linewidth=1.2, markersize=6,
                        linestyle="--", color=scene_colors[i], alpha=0.85)
                for si, s in enumerate(step_keys):
                    rng = ranges.get(s, {}).get(scene, {}).get(companion_mkey)
                    if rng is None:
                        continue
                    lo, hi = rng
                    if hi <= lo:
                        continue
                    col = scene_colors[i]
                    ax.vlines(si, lo, hi, color=col, alpha=0.35,
                              linewidth=1.0, linestyle=":", zorder=1)
                    ax.hlines(hi, si - tick_half, si + tick_half,
                              color=col, alpha=0.7, linewidth=1.8, zorder=2)
            comp_all_ys = []
            for si, s in enumerate(step_keys):
                vals, ws = [], []
                for scene, metrics in series[s].items():
                    v = metrics.get(companion_mkey)
                    if v is None:
                        continue
                    vals.append(v)
                    ws.append(_scene_weight(scene))
                comp_all_ys.append(sum(v * w for v, w in zip(vals, ws)) / sum(ws)
                                    if ws else None)
            ax.plot(x, comp_all_ys, marker="^", linewidth=1.6, markersize=7,
                    linestyle="--", color="#000000", zorder=6,
                    label=f"All {companion_mkey} (weighted)")

        if zeroline:
            ax.axhline(0.0, color="#888", linewidth=0.8, linestyle="--", zorder=0)
        if yscale == "symlog":
            ax.set_yscale("symlog", linthresh=lin_thresh)
            from matplotlib.ticker import ScalarFormatter
            fmt = ScalarFormatter()
            fmt.set_scientific(False)
            ax.yaxis.set_major_formatter(fmt)
            ax.yaxis.set_minor_formatter(ScalarFormatter(useOffset=False))
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels([f"step {s}\n{winners_label.get(s, '')[-30:]}"
                               for s in step_keys], fontsize=8, rotation=0)
    axes[0].legend(loc="upper right", fontsize=10)
    fig.suptitle(f"Ladder progression (x{spp} SPP)", fontsize=11)

    out = os.path.join(ladder_root, f"ladder_progress_x{spp}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[progress] {out}")
    return out


def plot_ladder_progress_combined(steps=None, spps=(1, 4)):
    """Compact cross-step progression: one weighted-"All" line per SPP
    (SCENE_WEIGHTS — 32PL × 3). Strips the per-scene lines, whiskers, and
    companion blob series that make the per-SPP plots dense — here the
    only purpose is to compare convergence behaviour across the ladder at
    different sample counts on a single figure.

    Output: captures/ladder/ladder_progress_combined.png.
    """
    import json, csv, glob
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ladder_root = "captures/ladder"
    # Steps 16-17 (skipped/retired) and the archive_post_alignment range
    # (18-29 + 31-52) are excluded from progression plots — measured under
    # earlier broken-cascade or stride-fragmented regimes, not comparable
    # to the current ladder. The new ladder steps 11-15 are included.
    # All step numbers are valid post-archive (steps 11-25+ are the current
    # ladder restart). The previous exclude list dropped pre-archive 11-52
    # which no longer exist on disk.
    _exclude = set()
    if steps is None:
        steps = []
        for p in sorted(glob.glob(os.path.join(ladder_root,
                                                  "[0-9][0-9]", "stats.csv"))):
            step_num = os.path.basename(os.path.dirname(p))
            if step_num in _exclude:
                continue
            steps.append(step_num)
    if not steps:
        print("[progress-combined] No step stats.csv files found.")
        return None

    # per_spp_series[spp][step] = {"rays":..., "err":..., "blob":..., "noise":...}
    per_spp_series = {s: {} for s in spps}
    winners_label = {}

    for step in steps:
        winner = _pick_step_winner_for_plot(step, ladder_root)
        if winner is None:
            continue
        winners_label[step] = winner
        rows_path = _step_csv(step)
        if not os.path.exists(rows_path):
            continue
        buckets = {s: {"rays": [], "err": [], "blob": [], "noise": [],
                        "weights": []} for s in spps}
        with open(rows_path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    row_spp = int(r.get("spp") or 1)
                except ValueError:
                    row_spp = 1
                if row_spp not in buckets:
                    continue
                if r["variant"] != winner:
                    continue
                def _f(k):
                    v = r.get(k, "")
                    try:
                        return float(v) if v not in ("", None) else None
                    except ValueError:
                        return None
                b = buckets[row_spp]
                for mk, ck in (("rays", "rays_traced_pct"),
                                ("err", "error_delta_pct"),
                                ("blob", "error_delta_blob_pct"),
                                ("noise", "noise_delta_pct")):
                    v = _f(ck)
                    if v is not None:
                        b[mk].append(v * _scene_weight(r["scene"]))
                    else:
                        b[mk].append(None)
                b["weights"].append(_scene_weight(r["scene"]))

        for s in spps:
            b = buckets[s]
            if not b["weights"]:
                continue
            wsum = sum(b["weights"])
            entry = {}
            for mk in ("rays", "err", "blob", "noise"):
                vals = [v for v in b[mk] if v is not None]
                if vals and wsum > 0:
                    entry[mk] = sum(vals) / wsum
            if entry:
                per_spp_series[s][step] = entry

    # Synthetic step-00 anchor (rays=100, err/noise/blob=0 by definition).
    for s in spps:
        if "00" in steps and "00" not in per_spp_series[s]:
            per_spp_series[s]["00"] = {"rays": 100.0, "err": 0.0,
                                         "blob": 0.0, "noise": 0.0}
    if "00" in steps and "00" not in winners_label:
        winners_label["00"] = "vanilla (baseline)"

    all_step_keys = [st for st in steps if any(st in per_spp_series[s] for s in spps)]
    if not all_step_keys:
        print("[progress-combined] No winner metrics found for any step.")
        return None
    x = list(range(len(all_step_keys)))

    fig, axes = plt.subplots(3, 1, figsize=(max(8, len(all_step_keys) * 2.0), 8),
                              sharex=True, constrained_layout=True,
                              gridspec_kw={"height_ratios": [1.0, 1.3, 0.6]})
    metric_defs = [
        ("rays",  "rays traced %",   False, None,    None,   RAYS_YLIM,          1.0),
        ("err",   "error Δ %",       True,  "symlog", "blob", ERROR_DELTA_YLIM,   3.0),
        ("noise", "noise Δ %",       True,  "symlog", None,   NOISE_DELTA_YLIM,   1.0),
    ]
    # Distinct hues per SPP — avoid recycling turbo since users expect SPP
    # to read "low → high sample count" monotonically.
    spp_colors = {1: "#1f77b4", 4: "#d62728", 16: "#2ca02c"}
    for ax, (mkey, ylabel, zeroline, yscale, companion_mkey, ylim, lin_thresh) in zip(axes, metric_defs):
        for s in spps:
            ys = [per_spp_series[s].get(st, {}).get(mkey) for st in all_step_keys]
            color = spp_colors.get(s, "#555555")
            ax.plot(x, ys, marker="D", linewidth=2.0, markersize=7,
                    color=color, label=f"x{s} SPP (All weighted)")
            if companion_mkey:
                cys = [per_spp_series[s].get(st, {}).get(companion_mkey)
                       for st in all_step_keys]
                ax.plot(x, cys, marker="^", linewidth=1.5, markersize=6,
                        linestyle="--", color=color, alpha=0.8,
                        label=f"x{s} {companion_mkey} (weighted)")
        if zeroline:
            ax.axhline(0.0, color="#888", linewidth=0.8, linestyle="--", zorder=0)
        if yscale == "symlog":
            ax.set_yscale("symlog", linthresh=lin_thresh)
            from matplotlib.ticker import ScalarFormatter
            fmt = ScalarFormatter(); fmt.set_scientific(False)
            ax.yaxis.set_major_formatter(fmt)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels([f"step {st}\n{winners_label.get(st, '')[-30:]}"
                               for st in all_step_keys],
                              fontsize=8, rotation=0)
    axes[0].legend(loc="upper right", fontsize=10, ncol=2)
    fig.suptitle(f"Ladder progression — weighted All, x{'+x'.join(str(s) for s in spps)} SPP",
                 fontsize=11)

    out = os.path.join(ladder_root, "ladder_progress_combined.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[progress] {out}")
    return out


def finalize_baseline(step_name="00"):
    """Step-00 end-of-run footer: emit baseline overview plots and mirror the
    summary PNG to the ladder root. Baseline analogue of `finalize_step` for
    absolute (non-delta) error/noise metrics."""
    plot_baseline_overviews(step_name)
    copy_summary_to_root(step_name)


def finalize_step(step_name, prev_winner=None, carried_winners=None,
                   inherited_winners=None, skip_overview=False,
                   ref_step=None, ref_variant=None, ref_label=None,
                   variant_filter=None):
    """Standard end-of-step footer: emit the per-metric overview plots and
    mirror summary PNGs to the ladder root. Also refreshes the cross-step
    ladder_progress.png so every finalize keeps it current.

    prev_winner: vestigial — no longer rendered in the title; inherited base
                 is marked visually with yellow circles (retired) / via the
                 inherited_winners halo set.
    carried_winners: variant names to highlight with a red circle (carried
                     forward to next step). Prefix match supported so full
                     variant names like "...__qA024_qB036" match their
                     suffixed descendants (e.g. "...__qA024_qB036__th2").
                     When None, auto-picks top-1 per B-variant.
    inherited_winners: variant names inherited from prior step (yellow halo —
                       retired but kept in signature for back-compat).
    skip_overview: skip combined overview + individual metric plots; callers
                   that use plot_overviews_per_bvariant / plot_top3_comparison
                   exclusively pass this True.
    ref_step / ref_variant / ref_label: optional reference overlay plumbed
                   to _plot_metric — shown as red stars at the referenced
                   variant's per-scene values.
    """
    if not skip_overview:
        plot_overviews(step_name, prev_winner=prev_winner,
                       carried_winners=carried_winners,
                       inherited_winners=inherited_winners,
                       ref_step=ref_step, ref_variant=ref_variant,
                       ref_label=ref_label,
                       variant_filter=variant_filter)
    copy_summary_to_root(step_name)
    # Cross-step progression stays in sync — it reads every step's CSV +
    # picks.json, so refreshing after each finalize keeps the ladder-root
    # summary consistent with latest per-step updates. Per-SPP plots (x1,
    # x4, x16) plus a compact combined-All overlay. Steps without x16 rows
    # simply show nothing on the x16 plot. Wrapped in try/except so a
    # progression-plot failure doesn't abort a successful step run.
    try:
        plot_ladder_progress(spp=1)
        plot_ladder_progress(spp=4)
        plot_ladder_progress(spp=16)
        plot_ladder_progress_combined(spps=(1, 4, 16))
    except Exception as e:
        print(f"[progress] skipped: {e}")


def copy_summary_to_root(step_name):
    """Mirror every overview_summary_<step>*.png from captures/ladder/<step>/
    into captures/ladder/ so all summaries (main + per-variant + top-N) sit at
    one level for cross-step comparison.
    Silent no-op if no summary files exist yet."""
    import glob
    src_dir = f"captures/ladder/{step_name}"
    copied = []
    for src in glob.glob(os.path.join(src_dir, f"overview_summary_{step_name}*.png")):
        dst = os.path.join("captures/ladder", os.path.basename(src))
        try:
            shutil.copy2(src, dst)
            copied.append(dst)
            print(f"[summary] {dst}")
        except (IOError, OSError):
            pass
    return copied or None


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
    # Filter by the effective-spp suffix (`.<spp>.exr` / `.<spp>.RGBA.exr`) so
    # repost calls don't mix .1/.4/.16 captures and pull the wrong frame's
    # mask. Live-render captures only have one SPP per dir so the filter is
    # a no-op there. spp=None disables the filter (legacy callers).
    raw_exrs = glob.glob(os.path.join(captureDir, f"{vn}.*.exr")) \
             + glob.glob(os.path.join(captureDir, "raw", f"{vn}.*.exr"))
    if spp:
        suf_plain = f".{spp}.exr"
        suf_rgba  = f".{spp}.RGBA.exr"
        exrs = [p for p in raw_exrs if p.endswith(suf_plain) or p.endswith(suf_rgba)]
        # Tolerate the legacy live-render naming (no SPP suffix) by falling
        # back to the unfiltered list when no SPP-tagged matches exist.
        if not exrs:
            exrs = raw_exrs
    else:
        exrs = raw_exrs

    # No-data masks: accum (fractional, from count+coldmissRate) vs frame (binary, from hashA+B==0)
    nd_accum = load_diag_mask(exrs, mode="nodata", total_frames=total_frames)
    nd_frame = load_diag_mask(exrs, mode="nodata_frame")

    # --- Compute global stats from EXR data ---
    stats = {"rays_traced_pct": -1.0, "coldmiss_pct": -1.0, "mean_level": None,
             "min_level": None, "max_level": None,
             "error_delta_pct": None, "error_delta_min_pct": None, "error_delta_max_pct": None,
             "error_delta_blob_pct": None, "error_delta_blob_sum_pct": None,
             "noise_delta_pct": None, "noise_delta_min_pct": None, "noise_delta_max_pct": None,
             "noise_delta_blob_pct": None}
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
        # Raw cascade level channel 0. Shader now writes raw g.level (not
        # pre-normalized) so we can stretch display to the observed min/max
        # range — makes narrow-band strided cascade usage visible.
        lv_data = cm_data  # already read above
        if lv_data is not None and lv_data.shape[2] >= 4:
            import numpy as np
            level_img = lv_data[:, :, 0]
            lv_mask = (nd_nohit > 0.5) if nd_nohit is not None else None
            valid = level_img >= 0  # shader writes -1 for coldmiss
            if lv_mask is not None:
                valid = valid & lv_mask
            if valid.any():
                stats["mean_level"] = float(level_img[valid].mean())
                stats["min_level"]  = float(level_img[valid].min())
                stats["max_level"]  = float(level_img[valid].max())
                # Normalize to [0,1] using observed range for colormap.
                lo = stats["min_level"]; hi = stats["max_level"]
                rng = max(hi - lo, 1.0)
                level_norm = np.where(valid, (level_img - lo) / rng, 0.0).astype(np.float32)
                # Write normalized level PNG directly (bypass _wc so we use the
                # normalized array rather than re-reading the EXR).
                from viscache_exr import viridis_png
                viridis_png(level_norm, o("r2c1_frame_level"), nodata=nd_nohit)
            else:
                stats["mean_level"] = float(level_img.mean())
                _wc(exr, 0, o("r2c1_frame_level"), nodata=nd_nohit)
        else:
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
    # The reusable `exrs` list above is already SPP-filtered; if a match is
    # there, prefer it. Fall back to a fresh glob (legacy live captures
    # without the SPP suffix) only if no SPP-tagged AccumulatePass EXR was
    # found — preventing a same-name variant's .1.exr from being read for
    # an x4/x16 row (was producing identical cache_err across SPP because
    # all rows ended up reading the .1 EXR).
    variant_hdr = find_exr(exrs, "AccumulatePass.output")
    if variant_hdr is None:
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
            stats["error_delta_blob_sum_pct"] = r.get("err_delta_blob_sum_pct")
            stats["error_artifact_pct"]   = r.get("err_artifact_pct")
            stats["vanilla_err_pct"]      = r.get("vanilla_err_pct")
            stats["vanilla_err_blob_pct"] = r.get("vanilla_err_blob_pct")
            stats["vanilla_err_artifact_pct"] = r.get("vanilla_err_artifact_pct")
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
        effective_spp, frames, warmup_first, warmup_run, subframe_n,
        stats["rays_traced_pct"], stats["coldmiss_pct"],
        stats.get("error_delta_pct"),
        stats.get("error_delta_min_pct"), stats.get("error_delta_max_pct"),
        stats.get("error_delta_blob_pct"),
        stats.get("noise_delta_pct"),
        stats.get("noise_delta_min_pct"), stats.get("noise_delta_max_pct"),
        mean_level=stats.get("mean_level"),
        error_delta_blob_sum_pct=stats.get("error_delta_blob_sum_pct"),
        min_level=stats.get("min_level"),
        max_level=stats.get("max_level"),
        vanilla_err_pct=stats.get("vanilla_err_pct"),
        vanilla_err_blob_pct=stats.get("vanilla_err_blob_pct"),
        error_artifact_pct=stats.get("error_artifact_pct"),
        vanilla_err_artifact_pct=stats.get("vanilla_err_artifact_pct"),
    )

    stats["variant"] = variant_name
    stats["scene"]   = scene_name
    stats["spp"]     = spp
    return stats


def run_variants(step_name, frame_configs, scene_file, variants=None,
                  maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None,
                  step_overrides=None, wipe_captures=True, resume=True):
    """Run all variants × frame configs for a ladder step.
    mogwai_globals: pass globals() from the Mogwai script to access m, fc, etc.
    step_overrides: dict merged on top of each variant's overrides (e.g. pMin).
    wipe_captures: if False, don't wipe the capture dir (for chained calls).
    resume: if True (default), consult the step CSV and skip variant×frame_config
            combos that already have a successful row. Wipe is suppressed when
            existing CSV rows are present so partial progress survives.
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

    completed_keys = _load_completed_keys(step_name, scene_name) if resume else set()

    # Wipe step×scene directory for clean output (unless chained or resuming).
    if wipe_captures and not completed_keys and os.path.exists(captureDir):
        shutil.rmtree(captureDir, ignore_errors=True)
    os.makedirs(captureDir, exist_ok=True)
    if completed_keys:
        print(f"[{step_name}] Resume: {len(completed_keys)} variant×config row(s) already complete for {scene_name}")

    all_stats = []
    for (variant_name, overrides) in variants:
        if step_overrides:
            # step_overrides applies step-level defaults (RR mode, cascade
            # config, table capacity); per-variant overrides explicitly tag
            # the swept axis (pMin, vt, ct, fp). Per-variant must win — the
            # earlier merge order silently clobbered every per-variant pMin
            # setting with RR_ADAPTIVE's pMin=0.05 floor, invalidating the
            # pMin sweeps in steps 13/16/19 (all variants ran at pMin=0.05).
            overrides = {**step_overrides, **overrides}
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
            # Tag encodes effective SPP (frames*spp). Capture filenames,
            # CSV key, and plot-group key all align on total samples/pixel.
            effective_spp = frames * spp
            tag = f"s_{frames}_x{effective_spp}_{warmupFirst}o{warmupRun}o{subN}x{subN}_{res_tag}"
            csv_key = f"{scene_name}_{tag}_{variant_name}"
            if csv_key in completed_keys:
                print(f"[{step_name}] Skip (resume): {variant_name} {tag}")
                continue
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
                             f"{_scene_prefix(scene_name)}{scene_name}_{xN_tag}_vanilla_plate.png")
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


# ===========================================================================
# Reconstructed session additions (plot helpers, picker, resume, chunking).
# Helpers below are defined textually so scripts/_recovery_diff.py can
# track reconstruction progress against the reference .pyc. Anything that
# is NOT yet reconstructed falls through to the safety-net block at the
# end of the file, which loads missing names from the intact session .pyc.
# ===========================================================================


def _b_core(variant_name):
    """Extract the B-side addressing core (pos / dir_dist1 / dir_dist / ...)
    from a variant name like 'pos_norm__dir_dist__qA012_qD15_qd048'."""
    parts = variant_name.split("__")
    if len(parts) > 1:
        return parts[1]
    return ""


def _add_adaptive_legend(target, handles, figlevel=False):
    """Place a legend outside the right edge. Scales columns + font to how
    many entries there are; above ~60 the per-variant legend is suppressed
    entirely (hue/saturation/alpha/shape already encode the axes, and the
    legend dwarfs the plot at that point). `target` is an Axes (figlevel=False)
    or a Figure (figlevel=True)."""
    if not handles:
        return
    n = len(handles)
    if n > 100:
        return
    if n <= 40:
        ncol, fs = 1, 9
    elif n <= 60:
        ncol, fs = 2, 8
    elif n <= 80:
        ncol, fs = 3, 7
    else:
        ncol, fs = 4, 6
    kwargs = dict(handles=handles, fontsize=fs, ncol=ncol, borderaxespad=0)
    if figlevel:
        target.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), **kwargs)
    else:
        target.legend(loc="upper left", bbox_to_anchor=(1.01, 1), **kwargs)


def _resolve_ref_rows(ref_step, ref_variant):
    """Load rows from another step's stats.csv, filtered by exact-match or
    prefix-match on the variant name. Returns [] if nothing matches.
    """
    if not ref_step or not ref_variant:
        return []
    rows = _load_step_rows(ref_step)
    if not rows:
        return []
    return [r for r in rows
            if r["variant"] == ref_variant or r["variant"].startswith(ref_variant)]


def _load_step_rows(step_name):
    """Load + type-coerce all rows from the step CSV. Returns [] if missing."""
    import csv
    csv_path = _step_csv(step_name)
    if not os.path.exists(csv_path):
        return []
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["rays_traced_pct"] = float(row["rays_traced_pct"])
            except (ValueError, KeyError):
                continue
            for k in ("coldmiss_pct",
                      "error_delta_pct", "error_delta_min_pct", "error_delta_max_pct",
                      "error_delta_blob_pct",
                      "noise_delta_pct", "noise_delta_min_pct", "noise_delta_max_pct"):
                v = row.get(k, "")
                try:
                    row[k] = float(v) if v not in ("", None) else None
                except ValueError:
                    row[k] = None
            try:
                row["spp"] = int(row.get("spp") or 1)
            except ValueError:
                row["spp"] = 1
            rows.append(row)
    return rows


def _load_completed_keys(step_name, scene_name):
    """Return the set of CSV 'key' values already recorded for (step, scene).
    Used by run_variants to skip variant×frame_config combos that a previous
    run completed — the step's CSV is upsert-keyed, so the presence of a key
    means render + postprocess + stats were all successful for that combo.
    """
    import csv
    path = _step_csv(step_name)
    if not os.path.exists(path):
        return set()
    keys = set()
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("scene") == scene_name and row.get("key"):
                    keys.add(row["key"])
    except (OSError, csv.Error):
        return set()
    return keys


def build_per_axis_quant_variants(base_preset, normal_a=60.0):
    """Return the 45-variant list used by step 03's per-axis quant sweep:
      pos_norm__pos         : qA × qB                = 9
      pos_norm__dir_dist1   : qA × qD (distB flat)   = 9
      pos_norm__dir_dist    : qA × qD × qd           = 27
    Shared helper so downstream steps can resolve step-03 winner names
    back to full override dicts without duplicating the construction.
    """
    variants = []
    for qA in PER_AXIS_QA:
        for qB in PER_AXIS_QB:
            tag = f"{_qA_tag(qA)}_{_qB_tag(qB)}"
            variants.append((f"pos_norm__pos__{tag}", {
                **base_preset,
                "enableVisCacheDirDistAddr": False,
                "enableVisCacheNormalAddr": True,
                "posACoarse": qA,
                "normalACoarse": normal_a,
                "posBCoarse": qB,
            }))
    for qA in PER_AXIS_QA:
        for qD in PER_AXIS_QD:
            tag = f"{_qA_tag(qA)}_{_qD_tag(qD)}"
            variants.append((f"pos_norm__dir_dist1__{tag}", {
                **base_preset,
                "enableVisCacheDirDistAddr": True,
                "enableVisCacheNormalAddr": True,
                "posACoarse": qA,
                "normalACoarse": normal_a,
                "dirBCoarse": qD,
                "distBCoarse": 1000.0,
            }))
    for qA in PER_AXIS_QA:
        for qD in PER_AXIS_QD:
            for qd in PER_AXIS_Qd:
                tag = f"{_qA_tag(qA)}_{_qD_tag(qD)}_{_qd_tag(qd)}"
                variants.append((f"pos_norm__dir_dist__{tag}", {
                    **base_preset,
                    "enableVisCacheDirDistAddr": True,
                    "enableVisCacheNormalAddr": True,
                    "posACoarse": qA,
                    "normalACoarse": normal_a,
                    "dirBCoarse": qD,
                    "distBCoarse": qd,
                }))
    return variants


def pick_top_variants_per_bvariant(step_name, n_top=3, spp=1):
    """Pick winners per B-variant by 'best ray savings with no scene outliers'.

    Rule (per-scene relative-best gate + absolute blob cap, unweighted rank):
      For EACH scene, compute the per-scene median err & blob across variants.
      A variant qualifies only if at EVERY scene:
        err  <= 0 OR err  <= median_err_scene  + 25% |median_err_scene|
        blob <= 0 OR blob <= median_blob_scene + 50% |median_blob_scene|
        AND blob <= 10.0 (absolute artifact cap: any blob > 10% is
                          outside target visual quality regardless of
                          how poorly other variants score)
      Then rank surviving variants by unweighted mean rays_traced ascending.

    This prevents a variant from winning by being great on average while
    regressing catastrophically on one scene. The absolute blob cap
    prevents a "best of a bad batch" carry when NO variant is actually
    close to target quality on some scene.

    Noise is informational only — gating on noise previously excluded
    otherwise-sensible candidates on <0.01 deltas.

    Returns {b_variant: [variant_name, ...]} — empty dict if CSV missing.
    """
    import statistics as stats
    rows = _load_step_rows(step_name)
    if not rows:
        return {}

    result = {}
    b_variants = sorted({_b_core(r["variant"]) for r in rows if _b_core(r["variant"])})
    for bv in b_variants:
        # per_scene[variant][scene] = {"rays", "err", "blob", "noise"}
        per_scene = {}
        for r in rows:
            if _b_core(r["variant"]) != bv or r["spp"] != spp:
                continue
            pv = per_scene.setdefault(r["variant"], {})
            pv[r["scene"]] = {
                "rays":  r.get("rays_traced_pct") or 0.0,
                "err":   r.get("error_delta_pct"),
                "blob":  r.get("error_delta_blob_pct"),
                "noise": r.get("noise_delta_pct"),
            }
        if not per_scene:
            result[bv] = []
            continue

        # Scenes represented for this B-variant (take superset across variants)
        all_scenes = sorted({s for pv in per_scene.values() for s in pv.keys()})

        # Per-scene medians + tolerances across variants at that scene
        scene_tol = {}
        for scn in all_scenes:
            errs  = [pv[scn]["err"]  for pv in per_scene.values()
                     if scn in pv and pv[scn]["err"]  is not None]
            blobs = [pv[scn]["blob"] for pv in per_scene.values()
                     if scn in pv and pv[scn]["blob"] is not None]
            if not errs or not blobs:
                continue
            med_e = stats.median(errs)
            med_b = stats.median(blobs)
            scene_tol[scn] = (med_e + 0.25 * abs(med_e),
                              med_b + 0.50 * abs(med_b))

        def _ok(val, tol):
            if val is None:
                return True
            return val <= 0.0 or val <= tol

        # Thresholds:
        #   ERR_HARD_CAP     — positive err delta above this is a reject. Signed
        #                      err can be misleading (average can go negative
        #                      from denoising while concentrated artifacts
        #                      exist), so this cap reflects "cache must not
        #                      hurt any scene more than 1% on average".
        #   BLOB_HARD_CAP    — visible artifact; variants exceeding on any
        #                      scene are rejected outright
        #   RAYS_HARD_CAP    — rays above this defeat the purpose of caching
        #                      (variant is near-vanilla); rejected outright
        # Weighted score for surviving variants:
        #   score = rays_mean + BLOB_WEIGHT × max_scene_blob + ERR_WEIGHT × max_scene_err
        ERR_HARD_CAP  = 1.0
        BLOB_HARD_CAP = 25.0
        RAYS_HARD_CAP = 50.0
        BLOB_WEIGHT   = 1.5   # a blob=10 worst scene adds 15pp to rays score
        ERR_WEIGHT    = 2.0   # a +5% err worst scene adds 10pp to rays score

        # Variant qualifies iff EVERY scene with data passes relative gates
        # AND every scene blob <= BLOB_HARD_CAP
        # AND aggregate rays <= RAYS_HARD_CAP.
        qualifying = []
        for v, pv in per_scene.items():
            all_pass = True
            max_scene_blob = 0.0
            max_scene_err  = 0.0
            for scn in all_scenes:
                if scn not in pv or scn not in scene_tol:
                    continue
                tol_e, tol_b = scene_tol[scn]
                blob_val = pv[scn]["blob"]
                err_val  = pv[scn]["err"]
                if not (_ok(err_val, tol_e)
                        and _ok(blob_val, tol_b)):
                    all_pass = False
                    break
                if blob_val is not None:
                    max_scene_blob = max(max_scene_blob, blob_val)
                    if blob_val > BLOB_HARD_CAP:
                        all_pass = False
                        break
                if err_val is not None:
                    if err_val > 0:
                        max_scene_err = max(max_scene_err, err_val)
                    if err_val > ERR_HARD_CAP:
                        all_pass = False
                        break
            if not all_pass:
                continue
            # Unweighted means over scenes for ranking / info
            rays_vals = [pv[scn]["rays"] for scn in all_scenes if scn in pv]
            err_vals  = [pv[scn]["err"]  for scn in all_scenes
                         if scn in pv and pv[scn]["err"]  is not None]
            blob_vals = [pv[scn]["blob"] for scn in all_scenes
                         if scn in pv and pv[scn]["blob"] is not None]
            nse_vals  = [pv[scn]["noise"] for scn in all_scenes
                         if scn in pv and pv[scn]["noise"] is not None]
            if not rays_vals:
                continue
            mean_rays = stats.mean(rays_vals)
            if mean_rays > RAYS_HARD_CAP:
                continue
            # Balance score: rays + blob-penalty + err-penalty. Lower = better.
            score = (mean_rays
                     + BLOB_WEIGHT * max_scene_blob
                     + ERR_WEIGHT  * max_scene_err)
            qualifying.append((v, {
                "rays":  mean_rays,
                "err":   stats.mean(err_vals)  if err_vals  else 0.0,
                "blob":  stats.mean(blob_vals) if blob_vals else 0.0,
                "noise": stats.mean(nse_vals)  if nse_vals  else 0.0,
                "max_scene_blob": max_scene_blob,
                "max_scene_err":  max_scene_err,
                "score": score,
            }))
        qualifying.sort(key=lambda kv: kv[1]["score"])
        result[bv] = [v for v, _ in qualifying[:n_top]]
    return result


def plot_overviews_per_bvariant(step_name, prev_winner=None, variant_filter=None):
    """For steps with multiple B-variants (pos / dir_dist1 / dir_dist), emit
    a separate overview_summary_<step>_<bvariant>.png for each, showing only
    that variant's rows. No-op if only one B-variant is present.

    variant_filter: optional callable(variant_name) -> bool. Extra per-row
    filter applied on top of B-variant grouping (used by step 03 to drop
    pos__dir_dist1 from the pos plot, etc.).

    Returns list of output paths (one per B-variant), or None if the step
    has no data or no split is needed.
    """
    rows = _load_step_rows(step_name)
    if not rows:
        print(f"[overview] per-variant: no data in step {step_name}")
        return None
    b_variants = sorted({_b_core(r["variant"]) for r in rows if _b_core(r["variant"])})
    if len(b_variants) <= 1:
        return None
    # Prefer picks.json (records manual overrides) over the live auto-picker.
    import json
    picks_path = os.path.join("captures", "ladder", step_name, "picks.json")
    if os.path.exists(picks_path):
        with open(picks_path) as f:
            meta = json.load(f)
        carried = meta.get("carried") or {}
        winners = {n for vs in carried.values() for n in vs}
    else:
        picks = pick_top_variants_per_bvariant(step_name, n_top=1, spp=1)
        winners = {v for vs in picks.values() for v in vs}
    # Rank-reference = the full step's variants so qA/qB/qD/qd rank maps are
    # identical across all B-variant splits. Without this, qA024 in `pos`
    # (ranked 2/4) would land a different hue than qA024 in `dir_dist`
    # (ranked 2/3 after the plot-subset filter).
    all_variants = sorted({r["variant"] for r in rows})
    outs = []
    for bv in b_variants:
        sub = [r for r in rows if _b_core(r["variant"]) == bv]
        if variant_filter is not None:
            sub = [r for r in sub if variant_filter(r["variant"])]
        if not sub:
            continue
        n_variants = len({r["variant"] for r in sub})
        title = f"B-variant pos_norm__{bv}  ({n_variants} configs)"
        out = _plot_combined(sub, step_name, prev_winner=prev_winner,
                              out_suffix=f"_{bv}", title_suffix=title,
                              winners=winners,
                              rank_reference_variants=all_variants)
        outs.append(out)
    return outs


def plot_top3_comparison(step_name, prev_winner=None, n_top=3):
    """Per-B-variant top-N quant winners combined into one comparison plot.
    Ranks each B-variant's variants by mean signed error_delta_pct at SPP=1
    across scenes (ascending — most-negative = best VisCache improvement).
    Keeps both SPP=1 and SPP=4 rows for the top-N variants; size channel
    distinguishes SPP in the plot.

    Output: captures/ladder/<step>/overview_summary_<step>_top<N>.png
    """
    picks = pick_top_variants_per_bvariant(step_name, n_top=n_top, spp=1)
    if not picks:
        print(f"[overview] top{n_top}: no data in step {step_name}")
        return None
    all_top = {v for vs in picks.values() for v in vs}
    best_per_bv = {vs[0] for vs in picks.values() if vs}
    rows = _load_step_rows(step_name)
    sub = [r for r in rows if r["variant"] in all_top]
    if not sub:
        return None
    # Rank-reference = full step's variants so the top-N palette matches the
    # per-B-variant split plots (qA024 has the same hue in every plot).
    all_variants = sorted({r["variant"] for r in rows})
    title = (f"Top-{n_top} quant per B-variant (ranked by median-gated rays "
             "savings at x1; x1 + x4 SPP shown)")
    out = _plot_combined(sub, step_name, prev_winner=prev_winner,
                          out_suffix=f"_top{n_top}", title_suffix=title,
                          winners=best_per_bv,
                          rank_reference_variants=all_variants)
    return out


def write_picks_meta(step_name, inherited_from=None, inherited=None,
                      carried=None, rule=None, notes=None):
    """Write captures/ladder/<step>/picks.json capturing which variants the
    step inherited from upstream and which it carries forward. Lets old CSV
    data be cross-referenced to the picker rule + picks that produced it.

    inherited_from: upstream step number string, e.g. "03".
    inherited: list of variant names inherited from that upstream step.
    carried: {b_variant: [variant_name, ...]} of picks forwarded to the next
             step. Mirrors pick_top_variants_per_bvariant's return shape.
    rule: short description of the picker rule in force.
    notes: optional free-form string.
    """
    import json, datetime
    out_dir = f"captures/ladder/{step_name}"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "picks.json")
    payload = {
        "step": step_name,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "rule": rule or "",
    }
    if inherited_from is not None:
        payload["inherited_from"] = inherited_from
    if inherited is not None:
        payload["inherited"] = list(inherited)
    if carried is not None:
        # Preserve manual carries: an empty dict (the step-script default)
        # never wipes out a hand-edited carries section. Re-running a step
        # to extend its scene coverage would otherwise erase the picks.
        if carried:
            payload["carried"] = {k: list(v) for k, v in carried.items()}
        elif os.path.exists(out):
            try:
                with open(out) as f_old:
                    old = json.load(f_old)
                payload["carried"] = old.get("carried") or {}
            except (json.JSONDecodeError, OSError):
                payload["carried"] = {}
        else:
            payload["carried"] = {}
    if notes:
        payload["notes"] = notes
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[picks] {out}")
    return out


# Variant-name tag parser — maps tag tokens (qA024, qB036, th2, jf05, vt020,
# …) back to the override-dict keys and values that produced them. Keeps
# variant names as the single source of truth for downstream steps: a step
# reads upstream picks.json → gets the carried variant name → parse_variant_tags
# rebuilds the numeric overrides, no hardcoded mirror of the upstream config.
_VARIANT_TAG_PATTERNS = {
    "posACoarse":    (r"qA(\d+)", lambda s: int(s) / 100.0),
    "posBCoarse":    (r"qB(\d+)", lambda s: int(s) / 100.0),
    "dirBCoarse":    (r"qD(\d+)", lambda s: float(s)),
    "distBCoarse":   (r"qd(\d+)", lambda s: int(s) / 100.0),
    "bootThreshold": (r"__ct(\d+)(?:__|$)", lambda s: int(s)),
    "jitterFilter":  (r"jf(\d+)", lambda s: int(s) / 10.0),
    "jitterCell":    (r"jc(\d+)", lambda s: int(s) / 10.0),
    # vt0 = 0.0001 ("trace on any non-zero variance modulo eps"); vt<N> = N/100.
    "varThreshold":  (r"vt(\d+)",
                      lambda s: 0.0001 if s == "0" else int(s) / 100.0),
    # se<N> = N/100 (stderrThreshold). se0 = 0.0001 sentinel.
    "stderrThreshold":  (r"se(\d+)",
                          lambda s: 0.0001 if s == "0" else int(s) / 100.0),
    # ad<N> = N/100 (accelDecayDisagreeThresh).
    "accelDecayDisagreeThresh": (r"ad(\d+)", lambda s: int(s) / 100.0),
    # hc0 / hc1 — hierarchicalConsistency off/on.
    "enableHierarchicalConsistency": (r"hc(\d+)", lambda s: bool(int(s))),
    # ctf<N> = bootThresholdFine (per-level fine variant of ct). 0 = off.
    "bootThresholdFine": (r"ctf(\d+)", lambda s: int(s)),
    # pm<N> = pMin (RR forced-trace floor). N/100. pm010=0.10, pm005=0.05.
    "pMin":                   (r"pm(\d+)", lambda s: int(s) / 100.0),
    # pa<N> = preinitAmbiguityCutoff (skip preinit if parent μ in
    # [cutoff, 1-cutoff]). pa0 = 0 = off; pa30 = 0.30.
    "preinitAmbiguityCutoff": (r"pa(\d+)", lambda s: int(s) / 100.0),
    # fd<N> = forceDescendFootprintPx (px^2 threshold). fd0 = off.
    "forceDescendFootprintPx": (r"fd(\d+k?)",
                                lambda s: int(s[:-1]) * 1024 if s.endswith("k") else int(s)),
}


def parse_variant_tags(name):
    """Reconstruct an override dict from a variant name.

    Recognises the standard tag tokens (qA/qB/qD/qd for quant, th for boot
    threshold, jf/jc for jitter, vt for varThreshold). Silently skips tokens
    that aren't present — callers merge this into their own base preset.
    """
    import re
    out = {}
    for key, (pat, cast) in _VARIANT_TAG_PATTERNS.items():
        m = re.search(pat, name)
        if m:
            out[key] = cast(m.group(1))
    return out


def read_carried_winner(step_name, b_variant="pos"):
    """Return the first carried variant name from a step's picks.json, or
    None if no picks.json exists / no carried entry for the B-variant.

    Intentionally does NOT fall back to the auto-picker — manual carries
    are meant to override the picker, so callers that want the auto result
    should call pick_top_variants_per_bvariant directly.
    """
    import json
    path = os.path.join("captures", "ladder", step_name, "picks.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        meta = json.load(f)
    carried = meta.get("carried") or {}
    names = carried.get(b_variant) or []
    return names[0] if names else None


# Text reconstruction complete — .pyc fallback retired 2026-04-22.
# VisCache_LadderCommon_session.pyc_backup kept as an audit artifact
# (scripts/_recovery_diff.py fingerprints compiled bytecode against it) but
# no longer loaded at runtime. Git-HEAD pre-session source preserved at
# VisCache_LadderCommon_githead.py.bak for historical reference.
