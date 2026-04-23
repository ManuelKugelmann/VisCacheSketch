"""
VisCache_Ladder17.py — Step 17: insert-side level skipping test.

Paper idea and step-12 spinoff: if the cascade's lookup refuses to
trust big cells (force-descend), why write them at all? The write-side
"skip coarse inserts at big footprints" halves hash-table pressure on
big-cell surfaces AND forces lookups to descend to meaningful finer
levels.

This step reuses `gForceDescendFootprintPx` as the gate. When set, the
shader now both:
  - Lookup: refuses to stop on convergence at big cells (existing).
  - Insert: skips writing at big cells, never populating them (new).

Minimal sweep on step-11 carry:
  - fd=0: baseline (both sides legacy) — baseline
  - fd=1024 (32×32 px): write+read skip at cells bigger than 32×32 px
  - fd=4096 (64×64 px): more conservative skip (only very big cells)

  3 fd × 2 SPP = 6 variants × 7 scenes = 84 runs.

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

INHERITED_NAME = read_carried_winner("11")
if INHERITED_NAME is None:
    raise RuntimeError("[17] step 11 picks.json missing — run step 11 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[17] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

FD_SWEEP = {"fd0": 0, "fd1k": 1024, "fd4k": 4096}

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_17 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VARIANTS_17 = []
for (name, base_overrides) in BASE_17:
    for fd_tag, fd_val in FD_SWEEP.items():
        tag = f"ct4_vt005_fp0_{fd_tag}_wrSkip"
        VARIANTS_17.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd_val,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        variants=VARIANTS_17,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="11", ref_variant=INHERITED_NAME,
              ref_label="step-11 carry (read-only legacy)")
write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Insert-side level-skip: at levels where cellPx > "
                        "forceDescendFootprintPx, the insert pass skips "
                        "writing (vs legacy which writes at every level). "
                        "Expected win: reduced table pressure on big-cell "
                        "surfaces + forces lookups to use meaningful finer "
                        "levels on those regions. Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True
