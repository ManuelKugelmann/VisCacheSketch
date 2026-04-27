"""
VisCache_Ladder20.py — Step 20: footprintScale sweep at ct=128 carry.

Inherits step-19 carry (= step-18 ct=128) pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm010.

Step 19 confirmed pMin is structurally no-op in the shader's current trust
logic — at trusted cells, the trace rate is 0 regardless of the pMin floor.
That rules out pMin as a rate-defense for x16 bias-floor artifacts on
Bistro/Sponza (blob 14-17 across all ct/pMin tested).

footprintScale is a different mechanism: it scales bootThreshold by
log2(cellPixels). Big cells (wide screen footprint) require proportionally
more samples before trust. Step 15 rejected footprintScale > 0 on 1PL/32PL
because it inflated rays without blob benefit there — but those were the
wrong test scenes. The x16 bias-floor on Bistro/Sponza is exactly the
"big-cell over-trust" pattern footprintScale targets: at 16 frames of
accumulation, coarse cells covering high-detail regions mature with
biased μ; footprintScale > 0 raises their trust threshold, forcing more
ray samples until the cell genuinely converges.

Sweep: footprintScale ∈ {0, 0.5, 1.0, 2.0}.

4 variants on 32PL+Bistro+Sponza. Cornell skipped — 1PL was the scene
that rejected fp>0 in step 15, and the fp=0 base case there is already
known-good (blob 9.6 at vt=0.03).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "20"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("19")
if INHERITED is None:
    raise RuntimeError("[20] step 19 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 128
VT_INH = 0.03
PM_INH = 0.10

BASE_20 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

FP_VALUES = [0.0, 0.5, 1.0, 2.0]

VARIANTS_20 = []
for (base_name, base_overrides) in BASE_20:
    for fp in FP_VALUES:
        # fp tag: 3-digit pct (fp000=0, fp005=0.5, fp010=1.0, fp020=2.0)
        fp_tag = f"fp{int(round(fp*10)):03d}"
        VARIANTS_20.append((f"{base_name}__bayer4x4_cell4x4_ct128_vt0030_pm010_{fp_tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": fp,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
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
        variants=VARIANTS_20,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="19", ref_variant=INHERITED,
              ref_label="step-19 carry (= step-18 ct128)")
write_picks_meta(STEP, inherited_from="19", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="footprintScale sweep at ct=128 carry to attack x16 "
                        "bias-floor on Bistro/Sponza. Step 15 rejected fp>0 "
                        "on 1PL/32PL but those were the wrong test scenes. "
                        "Big-footprint cells over-trust at x16 — fp scales "
                        "bootThreshold by log2(cellPixels). Optimum-in-"
                        "middle bet: fp=1.0.")
_HEADLESS_SCRIPT_DONE = True
