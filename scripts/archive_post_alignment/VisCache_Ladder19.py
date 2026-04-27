"""
VisCache_Ladder19.py — Step 19: directional addressing revisit for Sponza.

Under multi-frame, Sponza err is +13-26% across all (vt, pm, ct)
configs tested — cache fundamentally harmful. Step 27 / 11 / 12
confirm gate tuning cannot fix this; the problem is representational.

One unused dimension: `enableVisCacheDirDistAddr`. When ON, cache
cells split by direction-to-light AND distance-to-light in addition
to position+normal. A cell straddling a shadow boundary becomes two
separate cells: one for "shadow-facing" samples, one for "light-
facing". Biased μ stops existing at the boundary.

Archive steps 3 tested dir_dist single-level, but multi-level has
never been combined with dir_dist. This step probes:
  A: pos only (step-12 carry baseline)
  B: pos_dir (adds direction-to-light to addressing)
  C: pos_dir_dist (full directional)
  D: pos_dir_dist at coarser quant (more cells needed, coarser means
     larger hash load but each cell has more samples)

4 × 6 × 7 = 168 runs. Heavy memory usage; may need chunking if Bistro OOMs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 19
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "19"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[19] step 12 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[19] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

# Baseline overrides shared across variants (params set via base variant
# builder inject normal addressing; dir_dist we configure explicitly).
def _common(**extra):
    return {
        **NO_JITTER,
        "bootThreshold":                 CT_INH,
        "matureThreshold":               128,
        "varThreshold":                  VT_INH,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       0,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": False,
        "accelDecayDisagreeThresh":      0.0,
        "pMin":                          PM_INH,
        **QUANT_WINNER,
        **extra,
    }

tag = f"ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}"

VARIANTS_19 = [
    (f"pos_norm__pos__{_qa_tag}__{tag}_A_pos", _common(
        enableVisCacheDirDistAddr=False,
        enableVisCacheNormalAddr=True,
    )),
    (f"pos_norm__dir_dist__{_qa_tag}__{tag}_B_dirdist", _common(
        enableVisCacheDirDistAddr=True,
        enableVisCacheNormalAddr=True,
    )),
]

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 26}  # 2× capacity for dir_dist cells

MF_CONFIGS = [(1, 0, 1, 1),  (1, 0, 4, 1),  (1, 0, 16, 1),
              (2, 0, 1, 1),  (2, 0, 4, 1),  (2, 0, 16, 1)]

for scene_file in get_scenes(default=list(ALL_SCENES)):
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4, 16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=MF_CONFIGS,
        scene_file=scene_file,
        variants=VARIANTS_19,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (pos)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="dir_dist addressing revisit for Sponza bias. "
                        "Splits cells by direction-to-light + distance, "
                        "potentially separating shadow- vs light-facing "
                        "samples that previously averaged to biased μ. "
                        "Table capacity doubled to 2^26 for extra cells.")
_HEADLESS_SCRIPT_DONE = True
