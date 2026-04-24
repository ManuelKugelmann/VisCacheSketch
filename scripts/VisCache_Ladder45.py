"""
VisCache_Ladder45.py — Step 45: tMax-clamp fix retest.

HYPOTHESIS (user): pos addressing was broken for env/directional light
rays because `posB = posA + dir * tMax` had tMax ~= FLT_MAX, overflowing
the int32 cast in `round(pos/cellSize)`. That scrambled quant indices
for sun/env rays, which could be why Sponza (sun-lit) was terrible in
pos mode and dir_dist (which sidesteps the multiplication) magically
fixed it.

Fix: clamp dist to 32 × coarse-cell in vhfAddressPosB. Directional
rays now cluster by direction * finite_distance instead of by
arbitrary overflow pattern.

Repeat the step-43 ABCD triple-trial on Sponza. If the hypothesis is
right, A_pos_off should dramatically improve and match or beat
C_dirdist. If dir_dist still wins cleanly, the Sponza gain is a
different mechanism (likely real directional-addressing benefit).

  A_pos_off    — pos addressing, no HC, no decay
  B_pos_hc     — pos + HC peek
  C_dirdist    — dir_dist + HC peek
  D_full       — dir_dist + HC + decay dp15

4 × 3 trials × 3 spp × Sponza = 36 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "45"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS      = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

def common(hcOn, decayOn, decayPeriod):
    return {
        **NO_JITTER,
        "bootThreshold":                 4,
        "matureThreshold":               128,
        "varThreshold":                  0.01,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       16,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": hcOn,
        "hierarchicalMuTolerance":       0.20,
        "accelDecayDisagreeThresh":      0.0,
        "enableVisCacheDecay":           decayOn,
        "decayPeriod":                   decayPeriod,
        "pMin":                          PM_INH,
        "subframeN":                     4,
    }

VARIANTS_45 = []
for trial in (1, 2, 3):
    for (base_name, base_overrides) in BASE_POS:
        VARIANTS_45.append((f"{base_name}__A_pos_off__t{trial}", {
            **base_overrides, **common(False, False, 0)}))
    for (base_name, base_overrides) in BASE_POS:
        VARIANTS_45.append((f"{base_name}__B_pos_hc__t{trial}", {
            **base_overrides, **common(True, False, 0)}))
    for (base_name, base_overrides) in BASE_DIR_DIST:
        VARIANTS_45.append((f"{base_name}__C_dirdist__t{trial}", {
            **base_overrides, **common(True, False, 0)}))
    for (base_name, base_overrides) in BASE_DIR_DIST:
        VARIANTS_45.append((f"{base_name}__D_full__t{trial}", {
            **base_overrides, **common(True, True, 15)}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

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
        variants=VARIANTS_45,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="43", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Retest step-43 ABCD on Sponza after tMax-clamp "
                        "fix in vhfAddressPosB. Tests whether dir_dist's "
                        "Sponza win was sidestepping a latent int32 "
                        "overflow in pos-addressing for env/sun rays.")
_HEADLESS_SCRIPT_DONE = True
