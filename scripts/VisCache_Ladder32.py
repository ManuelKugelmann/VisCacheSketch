"""
VisCache_Ladder32.py — Step 32: tighten hierarchical-consistency tolerance.

Step 31 showed that peek HC with tolerance=0.20 barely changes blob relative
to HC off (1AL: 6.03 vs 6.63 — within noise). Hypothesis: 0.20 is too loose
to catch coarse-cell / fine-cell disagreement at shadow boundaries, where
both cells may straddle the penumbra similarly.

Sweep `hierarchicalMuTolerance` at fd=16, hc=on (peek-1-doubling-finer
already landed in step 31):

  a_tol005   — tol=0.05  (paranoid: peek-disagreement >5% → descend)
  b_tol010   — tol=0.10
  c_tol015   — tol=0.15
  d_tol020   — tol=0.20  (step-31 baseline for comparison)
  e_tol030   — tol=0.30  (looser; expect no peek hits → behaves like hc off)

5 × 3 spp × 7 scenes = 105 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "32"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("31") or read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[32] need step 31/22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[32] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

BASE_32 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, tol)
VARIANTS = [
    ("a_tol005",  0.05),
    ("b_tol010",  0.10),
    ("c_tol015",  0.15),
    ("d_tol020",  0.20),
    ("e_tol030",  0.30),
]

VARIANTS_32 = []
for (name, base_overrides) in BASE_32:
    for (suffix, tol) in VARIANTS:
        VARIANTS_32.append((f"{name}__ct4_fd16_hcOn_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       tol,
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
        variants=VARIANTS_32,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="31", ref_variant=INHERITED_NAME,
              ref_label="step-31 carry")
write_picks_meta(STEP, inherited_from="31", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Tighten hierarchicalMuTolerance at fd=16+hcOn. "
                        "Step 31 tol=0.20 + peek-1-doubling-finer barely "
                        "moved blob vs hc-off — hypothesis: tolerance too "
                        "loose to catch penumbra boundaries where both "
                        "adjacent levels straddle similarly. Sweep tight "
                        "→ loose to find where HC starts paying blob "
                        "rent for its ray cost.")
_HEADLESS_SCRIPT_DONE = True
