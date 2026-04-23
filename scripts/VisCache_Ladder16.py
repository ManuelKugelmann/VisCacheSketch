"""
VisCache_Ladder16.py — Step 16: per-level ct (bootThresholdFine) sweep.

Step 12 showed ct has opposite optima on Cornell 1PL (wants high ct
to defend penumbra blob) and Bistro (ct irrelevant for quality, lower
ct = fewer rays at matched err). Per-level ct is the design response:
coarse level HIGH ct (blob defense) + fine level LOW ct (cheap rays).

Shader change: `gBootThresholdFine` = lerp target at finest level.
When 0 (default), all levels use `gBootThreshold` uniformly (legacy).
When nonzero, effective ct at level L is `lerp(coarse, fine, L/(N-1))`.

Anchor on step-11 multi-level lineage (qa012 + ct4 + vt005 + fp0, no
jitter). Sweep (coarse ct, fine ct) pairs to see which configurations
improve Bistro rays without losing Cornell 1PL blob.

  Pairs (coarse, fine): (2,2), (4,4), (8,4), (16,4), (16,2), (32,2),
  (32,4), (64,4). 8 variants × 2 SPP × 4 scenes = 64 runs (Cornell
  only to start; big-scene supplement via -c "BistroInterior,…").

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 16
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "16"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("11")
if INHERITED_NAME is None:
    raise RuntimeError("[16] step 11 picks.json missing — run step 11 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[16] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

# (coarse_ct, fine_ct) pairs. When coarse == fine, behaves like legacy
# uniform ct; serves as baseline reference. When coarse > fine, the
# cascade starts strict at level 0 and relaxes toward fine levels —
# the design intent (blob defense at coarse, rays savings at fine).
CT_PAIRS = [
    (2, 2),   # baseline: uniform ct=2 (step-11 ct4 regression baseline)
    (4, 4),   # uniform ct=4 = step-11 carry equivalent
    (8, 4),   # mild asymmetry
    (16, 4),  # strong coarse, mild fine
    (16, 2),  # strong coarse, very loose fine
    (32, 2),  # very strict coarse, very loose fine
    (32, 4),  # very strict coarse, mild fine
    (64, 4),  # extreme coarse defense
]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_16 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VARIANTS_16 = []
for (name, base_overrides) in BASE_16:
    for (ct_coarse, ct_fine) in CT_PAIRS:
        # Tag: ct<coarse>_ctf<fine>_vt005_fp0. When ct_fine == ct_coarse,
        # the "ctf" is redundant but kept for consistency.
        tag = f"ct{ct_coarse}_ctf{ct_fine}_vt005_fp0"
        VARIANTS_16.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct_coarse,
            "bootThresholdFine":             ct_fine,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

# Default to Cornell scenes; big-scene supplement via -c override.
for scene_file in get_scenes(default=list(ALL_SCENES)):
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
        variants=VARIANTS_16,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="11", ref_variant=INHERITED_NAME,
              ref_label="step-11 carry (uniform ct=4)")
write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Per-level ct sweep (bootThreshold coarse, "
                        "bootThresholdFine at finest). Target: keep Cornell "
                        "1PL blob defense (needs high coarse ct) while "
                        "recovering Bistro rays savings (needs low fine ct). "
                        "Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True
