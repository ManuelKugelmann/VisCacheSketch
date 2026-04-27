"""
VisCache_Ladder16.py — Step 16: fd=1024 force-descend + insert-skip at
step-10 carry (multi-frame).

Archive step 17 v2 found fd=1024 (forceDescendFootprintPx with preinit-
preserving insert-skip) delivered 2-4pp rays savings on Bistro at ct=4
with mixed Cornell effects (1PL blob regressed 35→73). Under multi-frame,
the Bistro variance-dominated regime may benefit even more, and the 1PL
regression may reverse (samples now disperse across slots).

Four variants at step-10 carry (qa012+ct4, no pMin/vt changes):
  fd0    — baseline (current step-10 carry)
  fd1k   — skip inserts at cellPx > 1024
  fd4k   — skip inserts at cellPx > 4096 (conservative)
  fd1k_pm010 — combined: fd1k + pMin=0.10 (rate-defense + big-cell skip)

4 × 6 × 7 = 168 runs.

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

INHERITED_NAME = read_carried_winner("10")
if INHERITED_NAME is None:
    raise RuntimeError("[16] step 10 picks.json missing — run step 10 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[16] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_16 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (tag_suffix, fd_px, pm)
FD_VARIANTS = [
    ("fd0",          0,    0.05),
    ("fd1k",      1024,    0.05),
    ("fd4k",      4096,    0.05),
    ("fd1k_pm010", 1024,    0.10),
]

VARIANTS_16 = []
for (name, base_overrides) in BASE_16:
    for (suffix, fd, pm) in FD_VARIANTS:
        tag = f"ct{CT_INH}_vt005_{suffix}"
        VARIANTS_16.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          pm,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        variants=VARIANTS_16,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="10", ref_variant=INHERITED_NAME,
              ref_label="step-10 carry (fd=0)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="fd=1024 force-descend + insert-skip revisit at "
                        "multi-frame. Archive step 17 v2 showed 2-4pp "
                        "rays savings on Bistro at ct=4; Cornell 1PL "
                        "regressed single-frame but may recover under "
                        "multi-frame sample dispersion.")
_HEADLESS_SCRIPT_DONE = True
