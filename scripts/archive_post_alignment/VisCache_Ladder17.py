"""
VisCache_Ladder17.py — Step 17: variance-regime efficiency attack
(Bistro + 32PL low-ct) under multi-frame.

Archive step 21 found ct=4+pm010 halved 32PL rays (83→46 at x1, 40→17
at x4) with negligible quality loss. The pair was rejected as a
universal carry because Sponza regressed. Under multi-frame, the
cache accumulates across frames with real Bayer dispersion, so
variance-dominated scenes (Bistro, 32PL) may tolerate even lower ct
and maintain quality.

Five variants pushing ct down aggressively:
  ct2  — minimum tested in archive step 10 (ct=2 was there); wins rays
  ct4  — step-10 carry baseline
  ct2_pm010 — ct2 with rate-defense
  ct2_vt001 — ct2 with tighter convergence
  ct2_fd1k  — ct2 with big-cell skip

Target scenes: this step runs default (Cornell) but the REAL answer
is at Bistro+32PL. Follow with `-c Bistro*,Sponza` run to see if any
ct=2 variant can survive Sponza.

5 × 6 × 7 = 210 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 17
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "17"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("10")
if INHERITED_NAME is None:
    raise RuntimeError("[17] step 10 picks.json missing — run step 10 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[17] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_17 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (tag_suffix, ct, vt, fd, pm)
EFFICIENCY_VARIANTS = [
    ("ct2_vt005_fd0_pm005",    2, 0.05,    0, 0.05),
    ("ct4_vt005_fd0_pm005",    4, 0.05,    0, 0.05),
    ("ct2_vt005_fd0_pm010",    2, 0.05,    0, 0.10),
    ("ct2_vt001_fd0_pm010",    2, 0.01,    0, 0.10),
    ("ct2_vt005_fd1k_pm010",   2, 0.05, 1024, 0.10),
]

VARIANTS_17 = []
for (name, base_overrides) in BASE_17:
    for (suffix, ct, vt, fd, pm) in EFFICIENCY_VARIANTS:
        VARIANTS_17.append((f"{name}__{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct,
            "matureThreshold":               128,
            "varThreshold":                  vt,
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
        variants=VARIANTS_17,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="10", ref_variant=INHERITED_NAME,
              ref_label="step-10 carry (ct4)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Variance-regime efficiency attack. Under multi-"
                        "frame's proper sample dispersion, ct=2 may now "
                        "deliver the rays savings that archive step 21 "
                        "showed at ct=4. Target: Bistro/32PL rays cuts.")
_HEADLESS_SCRIPT_DONE = True
