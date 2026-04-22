"""
VisCache_Ladder07.py — Step 07: stderr gate sensitivity curve, SINGLE-LEVEL.

The principled replacement for step 06's `varThreshold` gate: instead of
gating on cell variance alone (which trusts few-sample cells with spurious
low var), gate on Bernoulli standard error — sqrt(var/N). A cell is
trusted only when it has both low variance AND enough samples.

Step 06's vt sweep bakes in the step-05 quant+ct carry (qA024_qB036 + ct2).
Step 07 uses the same base but varies only stderrThreshold (se). When
stderrThreshold > 0, the shader's convergence gate switches from
`var ≤ varThreshold` to `sqrt(var/N) ≤ stderrThreshold`. varThreshold is
kept at 0.05 as a weak floor but is largely overridden.

Mirror multi-level step with hc / ad combined = step 15.

Sweep values: {0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30}. Tag:
se<value×100 pad-3>, so se010, se030, se050, se080, se100, se150, se200,
se300. Below se050 the gate is conservative (trusts only well-converged
cells); above se100 it approaches the vt010 regime for high-sample cells.

  8 se × 2 SPP = 16 runs/scene × 4 scenes = 64 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 07
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, pick_top_variants_per_bvariant, write_picks_meta, \
    read_carried_winner, parse_variant_tags, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "07"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("05")
if INHERITED_NAME is None:
    raise RuntimeError("[07] step 05 picks.json missing — run step 05 first.")
INHERITED = parse_variant_tags(INHERITED_NAME)
NORMAL_A = 60.0

BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    "matureThreshold": 128,
    "varThreshold": 0.05,  # weak floor; overridden when stderrThreshold > 0
    **INHERITED,
}

SE_VALUES = [0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]
NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

def _se_tag(v):
    return f"se{int(round(v * 100)):03d}"

VARIANTS_07 = [
    (f"{INHERITED_NAME}__{_se_tag(se)}", {
        **BASE,
        **NO_JITTER,
        "stderrThreshold":               se,
        "enableHierarchicalConsistency": False,
        "accelDecayDisagreeThresh":      0.0,
    })
    for se in SE_VALUES
]

STEP_OVERRIDES = {**RR_ADAPTIVE, **SUBFRAME_2x2}

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_07,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="06", ref_variant=None,
              ref_label="step-06 vt carry (compare curve)")
_carried = pick_top_variants_per_bvariant(STEP, n_top=1, spp=1)
write_picks_meta(STEP, inherited_from="05", inherited=[INHERITED_NAME],
                  carried=_carried, rule=_DEFAULT_PICKER_RULE,
                  notes="Pure stderrThreshold sensitivity curve on step-05 "
                        "carry. Single-level mirror of step 06's vt sweep, "
                        "using the principled Bernoulli stderr criterion "
                        "(trust iff sqrt(var/N) ≤ se).")
_HEADLESS_SCRIPT_DONE = True
