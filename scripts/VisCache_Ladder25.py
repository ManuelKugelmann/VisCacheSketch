"""
VisCache_Ladder25.py — Step 25: tighter vt limit probe (vt001 / vt002 / vt003).

Step 23 locked vt003 as the carry with Sponza x4 err parity (+0.17%).
This step probes whether tighter vt extends the Sponza gain further,
or if vt003 is already the local optimum.

Three variants: vt001 / vt002 / vt003 (baseline). 3 × 6 × 7 = 126 runs.

If vt002 or vt001 pushes Sponza below vanilla (negative err delta),
carry the tighter value. Cost: tighter vt means p=var/vt rises so RR
forced-trace fires more often — expect +1-3pp rays.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 25
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "25"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("23")
if INHERITED_NAME is None:
    raise RuntimeError("[25] step 23 picks.json missing — run step 23 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[25] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_25 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VT_SWEEP = {"vt001": 0.01, "vt002": 0.02, "vt003": 0.03}

VARIANTS_25 = []
for (name, base_overrides) in BASE_25:
    for vt_tag, vt_val in VT_SWEEP.items():
        tag = f"ct16_{vt_tag}_fp0_fd0_pm010"
        VARIANTS_25.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  vt_val,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          0.10,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        frame_configs=[(1, 0, 1, 1),  (1, 0, 1, 4),  (1, 0, 1, 16),
                       (2, 0, 1, 1),  (2, 0, 1, 4),  (2, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_25,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="23", ref_variant=INHERITED_NAME,
              ref_label="step-23 carry (vt003)")
write_picks_meta(STEP, inherited_from="23", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Tighter vt limit probe. Step 23 showed vt003 at "
                        "pm010 gives Sponza x4 err parity. Does vt002 or "
                        "vt001 extend the gain further? Carry if Sponza "
                        "goes below vanilla.")
_HEADLESS_SCRIPT_DONE = True
