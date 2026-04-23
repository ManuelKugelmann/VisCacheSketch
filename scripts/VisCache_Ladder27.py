"""
VisCache_Ladder27.py — Step 27: re-measure step-23 carry under multi-frame.

All prior ladder x4/x16 data used `(frames=1, spp=N)` — one frame with
N samples per pixel, which traps every sample at the same Bayer slot.
Going forward, viscache runs always use spp=1 and dispense temporal
dispersion via frames=N. This step re-measures the step-23 carry
under the corrected regime on all 7 scenes.

Single variant (`ct16_vt003_fp0_fd0_pm010`), frame configs:
  x1  → (wf, 0, 1, 1)
  x4  → (wf, 0, 4, 1)   (was: 1, 4)
  x16 → (wf, 0, 16, 1)  (was: 1, 16)

Compare against step 23's single-frame numbers to quantify the
impact. If the delta is large on x16 (expected: big drop in 1PL/
Sponza error), all x4/x16 data in steps 10-25 needs refreshing.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 27
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "27"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("23")
if INHERITED_NAME is None:
    raise RuntimeError("[27] step 23 picks.json missing — run step 23 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[27] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_27 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VARIANTS_27 = []
for (name, base_overrides) in BASE_27:
    tag = "ct16_vt003_fp0_fd0_pm010"
    VARIANTS_27.append((f"{name}__{tag}", {
        **base_overrides,
        **NO_JITTER,
        "bootThreshold":                 16,
        "matureThreshold":               128,
        "varThreshold":                  0.03,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       0,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": False,
        "accelDecayDisagreeThresh":      0.0,
        "pMin":                          0.10,
    }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

# Multi-frame configs — spp=1 always, frames=N encodes dispersion.
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
        variants=VARIANTS_27,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="23", ref_variant=INHERITED_NAME,
              ref_label="step-23 carry (single-frame)")
write_picks_meta(STEP, inherited_from="23", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Step-23 carry re-measured under multi-frame x4/x16 "
                        "(frames=N, spp=1). All prior ladder x4/x16 data "
                        "used frames=1, spp=N — same Bayer slot for all "
                        "samples, no temporal dispersion. Viscache from now "
                        "on: always spp=1, use frames for multi-sample. "
                        "If this step shows material delta on x16 Sponza/"
                        "1PL, all step-10-25 x4/x16 data needs refreshing.")
_HEADLESS_SCRIPT_DONE = True
