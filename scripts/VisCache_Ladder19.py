"""
VisCache_Ladder19.py — Step 19: re-test fd=1024 × ct16+w2 under insert-skip shader.

Step 12 originally tested fd=1024 × ct=16+w=2 and the notes read
"force-descend (fd1k) is a no-op here". But step 12 ran under the
lookup-only fd shader — step 17 v2 extended `forceDescendFootprintPx`
to the INSERT side too (with preinit-preservation). Under the new
shader, fd=1024 both refuses to stop lookup on converged big cells
*and* skips writing to them.

Step 17 v2 confirmed fd=1024 saves 2-4pp rays on Bistro with ct=4,
but regressed 1PL blob 35→73. Hypothesis: ct=16 (more samples before
trust) cushions the finer-level data starvation that comes from
skipping coarse writes. If true: Bistro saves rays AND 1PL holds.

Two variants (mirror of step 18 size):
  fd0   — step-12 carry verbatim (ct16_vt005_fp0_fd0, w=2)
  fd1k  — step-12 carry + insert-skip at cellPx > 1024

Frame configs match step 12: x1/x4/x16 × w=1/w=2.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 19
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "19"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[19] step 12 picks.json missing — run step 12 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[19] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_19 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

FD_SWEEP = {"fd0": 0, "fd1k": 1024}

VARIANTS_19 = []
for (name, base_overrides) in BASE_19:
    for fd_tag, fd_val in FD_SWEEP.items():
        tag = f"ct16_vt005_fp0_{fd_tag}"
        VARIANTS_19.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd_val,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
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
        variants=VARIANTS_19,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (fd=0)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Targeted 2-variant test: does fd=1024 stack with "
                        "step-12's ct16+w=2 carry under the step-17-v2 "
                        "insert-skip shader? Step 17 v2 showed fd=1024 saves "
                        "2-4pp rays on Bistro with ct=4 but regressed 1PL "
                        "blob 35→73. Hypothesis: ct=16 cushions the fine-level "
                        "starvation. Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True
