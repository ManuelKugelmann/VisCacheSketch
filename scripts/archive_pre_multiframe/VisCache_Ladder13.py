"""
VisCache_Ladder13.py — Step 13: stderr gate + hierarchical check + accel decay
(SINGLE-LEVEL, step-06 carry lineage).

Tests three new shader mechanisms landed after step 12, at single-level
(step-06's operating point) so we isolate their effect from cascade
complexity. Multi-level mirror is step 15.

Single-level carry from step 06: qA024_qB036 + ct2 + vt005.

Axes:
  - se (stderrThreshold) ∈ {0.05, 0.10, 0.15, 0.20}. 0 = fall back to vt;
    we sweep positive values. The principle: trust iff sqrt(var/N) ≤ se,
    which combines "low variance" and "enough samples" into one check.
  - hc (hierarchicalConsistency) ∈ {off, on}. Peek next level for μ
    agreement. On single-level it's a no-op at level 0 — included here as
    a control (should be identical to hc0).
  - ad (accelDecayDisagreeThresh) ∈ {0, 0.5}. 0 = off. 0.5 means samples
    differing from cell μ by >0.5 trigger in-insert half-decay.

  4 se × 2 hc × 2 ad = 16 variants × 2 SPP = 32 runs/scene × 4 scenes = 128.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 13
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "13"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("06")
if INHERITED_NAME is None:
    raise RuntimeError("[13] step 06 picks.json missing — run step 06 first.")
INHERITED = parse_variant_tags(INHERITED_NAME)
NORMAL_A = 60.0

BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    "matureThreshold": 128,
    **INHERITED,
}

SE_SWEEP = {"se05": 0.05, "se10": 0.10, "se15": 0.15, "se20": 0.20}
HC_SWEEP = {"hc0": False, "hc1": True}
AD_SWEEP = {"ad0": 0.0, "ad50": 0.5}

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

VARIANTS_13 = []
# Build tag suffix from INHERITED_NAME — reuse the qA/qB/ct part.
# Variant names: <inherited>__<se>_<hc>_<ad>
for se_tag, se_val in SE_SWEEP.items():
    for hc_tag, hc_val in HC_SWEEP.items():
        for ad_tag, ad_val in AD_SWEEP.items():
            tag = f"{se_tag}_{hc_tag}_{ad_tag}"
            VARIANTS_13.append((f"{INHERITED_NAME}__{tag}", {
                **BASE,
                **NO_JITTER,
                "stderrThreshold":               se_val,
                "enableHierarchicalConsistency": hc_val,
                "accelDecayDisagreeThresh":      ad_val,
            }))

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
        variants=VARIANTS_13,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="06", ref_variant=INHERITED_NAME,
              ref_label="step-06 single-level carry")
write_picks_meta(STEP, inherited_from="06", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="stderr × hierarchical × accel-decay sweep on step-06 "
                        "single-level carry. Target: validate stderr as a "
                        "replacement for vt. Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True
