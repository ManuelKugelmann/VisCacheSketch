"""
VisCache_Ladder22.py — Step 22: cell-size sweep at ct=128/pm020/hc005 carry.

Inherits step-21 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm020_hc005.

Steps 19-21 confirmed all *trust defenses* (pMin, footprintScale, HC) leave
Bistro/Sponza x16 blob at 14-21 (artifact territory). Adding rays or
cross-checks doesn't fix the cached values. The remaining hypothesis:
**cell size is too coarse** — qa012 (=0.12 of scene avgAxis) cells span
visibility transitions, so any μ they store is the average of mixed
visibility states, biased away from any individual pixel's true value.
Smaller cells reduce intra-cell averaging and give the trust gates room
to actually distinguish converged from un-converged cells.

Sweep: posACoarse ∈ {0.12, 0.24, 0.48}.

posACoarse is the coarse-end quant of the position-A axis. Smaller value
= more cells per scene = each cell smaller. The cascade still goes finer
from there (LEVELS_MULTI configures the fine end), so this controls the
*top-of-cascade* cell size.

3 variants on 32PL+Bistro+Sponza. Optimum-in-middle bet: qa024.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "22"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("21")
if INHERITED is None:
    raise RuntimeError("[22] step 21 picks.json missing carried winner.")

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 128
VT_INH = 0.03
PM_INH = 0.20

# Sweep top-of-cascade cell size. QUANT_SWEEP keys are qa006 (finest),
# qa012 (current carry), qa036 (coarser). Smaller posA = finer cells.
# Format keys: posA / normalA / posB / dirB / distB (not the *Coarse names).
QA_TAGS = ["qa006", "qa012", "qa036"]

VARIANTS_22 = []
for qa_tag in QA_TAGS:
    quant = QUANT_SWEEP[qa_tag]
    base_list = make_norm_variants(quant=quant, base=PRESET_MINIMAL,
                                    quant_tag=qa_tag)
    base = next(v for v in base_list if v[0] == f"pos_norm__pos__{qa_tag}")
    base_name, base_overrides = base
    VARIANTS_22.append((f"{base_name}__bayer4x4_cell4x4_ct128_vt0030_pm020_hc005", {
        **base_overrides,
        **NO_JITTER,
        "bootThreshold":                 CT_INH,
        "matureThreshold":               max(128, CT_INH),
        "varThreshold":                  VT_INH,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       FD,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": True,
        "hierarchicalMuTolerance":       0.05,
        "accelDecayDisagreeThresh":      0.0,
        "pMin":                          PM_INH,
        "subframeN":                     SUBFRAME_N,
    }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(MULTI_LEVEL_SCENES)):
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
        variants=VARIANTS_22,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="21", ref_variant=INHERITED,
              ref_label="step-21 carry (qa012 + hc005)")
write_picks_meta(STEP, inherited_from="21", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Cell-size sweep at ct=128/pm020/hc005. qa {0.12, "
                        "0.24, 0.48}. Trust defenses (pMin/fp/HC) couldn't "
                        "fix x16 artifacts; the structural cause may be "
                        "qa012 cells spanning visibility transitions. "
                        "Smaller cells = less intra-cell averaging. "
                        "Optimum-in-middle bet: qa024.")
_HEADLESS_SCRIPT_DONE = True
