"""
VisCache_Ladder13.py - Step 13: vt × ct × pm sweep [DEAD-END KEPT FOR DOC].

STATUS: vt axis turned out empirically redundant in [0.01, 0.08] — Bernoulli
variance = μ(1−μ) is a function of μ alone, so any tight vt categorically
rejects penumbra cells (μ in middle range) and the exact threshold within
the tight band doesn't matter. pm=0.02 dominated pm=0.10 by ~3× more
savings. ct axis was useful only at fd=16 (ct=16 winner at x16 SPP).
Step 14 supersedes this with the actual fd × ct sweep.

Key insight (user 2026-04-27): for Bernoulli RV, var = μ(1−μ).
Only μ near 0 (fully shadowed) or μ near 1 (fully lit) gives low
variance. Penumbra cells (any intermediate μ) are intrinsically
untrustworthy regardless of how many samples they accumulate — the
variance reflects irreducible uncertainty about THIS particular ray's
outcome, not sampling noise. So vt IS the correct gate.

Step 12 cascade-on showed 99.8-100% rays traced on CornellBox_1AreaLight.
That's because the area light produces mostly penumbra (no pure-shadow
or pure-lit regions large enough to populate). vt=0.03 correctly rejects
all those cells.

Step 13 strategy:
1. Test on hard-shadow scenes (1PointLight, 32PointLights) where there
   ARE large pure-shadow regions vt can save rays in.
2. Sweep vt around 0.03 to find sweet spot — too tight rejects useful
   near-pure cells, too loose trusts penumbra-edge cells (artifacts).
3. Sweep ct (boot threshold) — bigger cells need fewer frames to mature
   so ct can be bigger without hurting time-to-converge.
4. Sweep pm (RR floor) — lower pm = more aggressive savings on
   trusted cells.

Single fd=16 (cell4x4, matched with bayer 2x2) for axis isolation.
Sweep on 2 scenes for cross-scene robustness.

Sweep matrix:
  vt ∈ {0.01, 0.03, 0.08}   (tight to slightly loose; max Bernoulli var = 0.25)
  ct ∈ {16, 64}             (1x, 4x of fd=16)
  pm ∈ {0.02, 0.10}         (aggressive vs default)
  = 12 variants

Scenes: CornellBox_1PointLight + CornellBox_32PointLights (hard shadows).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "13"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("10")
if INHERITED is None:
    raise RuntimeError("[13] step 10 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
BAYER_N = 2    # bayer 2x2 (4 slots)
FD = 16           # cell4x4 - matched with bayer 2x2

VT_VALUES = [0.01, 0.03, 0.08]   # tight, baseline, slightly loose
CT_VALUES = [16, 64]             # 1x, 4x of fd=16
PM_VALUES = [0.02, 0.10]         # aggressive vs baseline

DEFAULT_SCENES = ["CornellBox_1PointLight", "CornellBox_32PointLights"]

BASE_13 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS_13 = []
for (base_name, base_overrides) in BASE_13:
    for vt in VT_VALUES:
        for ct in CT_VALUES:
            for pm in PM_VALUES:
                vt_tag = f"vt{int(round(vt*1000)):03d}"
                ct_tag = f"ct{ct:03d}"
                pm_tag = f"pm{int(round(pm*100)):03d}"
                tag = f"bayer{BAYER_N}x{BAYER_N}_cell4x4_{ct_tag}_{vt_tag}_{pm_tag}"
                VARIANTS_13.append((f"{base_name}__{tag}", {
                    **base_overrides,
                    **NO_JITTER,
                    "bootThreshold":                 ct,
                    "matureThreshold":               max(128, ct * 2),
                    "varThreshold":                  vt,
                    "stderrThreshold":               0.0,    # off; vt does the work
                    "bootThresholdFactorFootprintPx": 0.0,
                    "forceDescendFootprintPx":       FD,
                    "enableHierarchicalConsistency": False,  # off this step
                    "hierarchicalMuTolerance":       0.20,
                    "accelDecayDisagreeThresh":      0.0,
                    "pMin":                          pm,
                    "bayerN":                        BAYER_N,
                    "enableDecayAutoTune":           False,
                }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
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
        variants=VARIANTS_13,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="10", ref_variant=INHERITED,
              ref_label="step-10 carry (qa012/ct4)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="vt × ct × pm sweep on hard-shadow scenes "
                        "(1PointLight + 32PointLights). VisCache only saves "
                        "rays in pure-shadow / pure-lit regions because "
                        "Bernoulli variance reflects irreducible per-ray "
                        "uncertainty in penumbra. Hard-shadow scenes have "
                        "more pure regions for vt to trust; area-light "
                        "scenes (1AreaLight) saturate at 100% rays.")
_HEADLESS_SCRIPT_DONE = True
