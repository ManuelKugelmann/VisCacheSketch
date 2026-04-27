"""
VisCache_Ladder33.py — Step 33: stderr gate on top of HC peek + analytical entry.

Step 32 found fd16 + hcOn + tol=0.20 best-so-far on Sponza (x1 blob 148 →
83, −45%). Hypothesis for remaining Sponza blob: premature convergence on
low-sample cells where Bernoulli var ≈ 0 from luck, not maturity.

stderrThreshold gates convergence on sqrt(var/N) instead of var alone:
  var ≤ vt              → converges at mu ≈ 0 or 1 regardless of N
  sqrt(var/N) ≤ se      → requires ≥ var/se² samples before trust

At mu=0.05 (one hit in 20 true-visible cells wrongly all-miss), var=0.05,
se=0.03 → need N ≥ 0.05/0.0009 ≈ 56 samples. Way more than var-gate's
instant acceptance.

Sweep four stderrThreshold values at fd16+hc+tol020:

  a_se000   — stderrThreshold=0 (var gate only, step-32 baseline)
  b_se003   — 0.03  (strict — need ~60 samples at mu≈0.05)
  c_se005   — 0.05  (moderate — need ~20)
  d_se010   — 0.10  (lax — need ~5)

4 × 3 spp × 5 scenes = 60 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "33"
res = int(os.environ.get("RES", "512"))

# Steps 22/31/32 all leave picks.json with carried={} (no auto-winner survived
# the gates). The inherited name from step 22's ladder is the stable reference.
INHERITED_NAME = "pos_norm__pos__qa012__ct4_vt001_fp0_fd0_pm005_sub4"

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[33] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

BASE_33 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, stderr)
VARIANTS = [
    ("a_se000", 0.00),
    ("b_se003", 0.03),
    ("c_se005", 0.05),
    ("d_se010", 0.10),
]

VARIANTS_33 = []
for (name, base_overrides) in BASE_33:
    for (suffix, se) in VARIANTS:
        VARIANTS_33.append((f"{name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               se,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

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
        variants=VARIANTS_33,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="32", ref_variant=INHERITED_NAME,
              ref_label="step-32 carry")
write_picks_meta(STEP, inherited_from="32", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="stderr gate sweep on step-32 carry. Hypothesis: "
                        "remaining Sponza blob comes from premature "
                        "convergence on low-sample cells (var-gate triggers "
                        "when mu≈0 regardless of N). stderrThreshold gates "
                        "on sqrt(var/N) ≤ se, forcing real sample density "
                        "before trust.")
_HEADLESS_SCRIPT_DONE = True
