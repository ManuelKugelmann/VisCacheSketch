"""
VisCache_Ladder26.py — Step 26: footprint factor (fp) sweep at sub4 carry.

User observation: Sponza shows large cells that don't get refined.
The bootThresholdFactorFootprintPx (fp) parameter scales trust
threshold by `fp * log2(cellPx)` — making large cells require many
more samples before trust, forcing cascade descent to finer levels.

Currently fp=0 (off) in the carry. Archive step 17 v2 tested fd
(force-descend) at ct=4 with mixed Cornell/Bistro results. Now under
sub4 carry (which already fixed Sponza err to -3.7%), test if
footprint factor reduces the residual large-cell visibility blob
that's still 145-160 on Sponza.

Four variants at sub4 carry:
  fp00       — baseline (current carry)
  fp10       — paper default (fp=1.0)
  fp20       — aggressive (fp=2.0)
  fp10_fd1k  — fp=1.0 + force-descend at cellPx>1024

4 × 3 spp × 7 scenes = 84 runs. Uses w=0 per step-25 finding.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 26
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "26"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[26] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[26] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_26 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, fp factor, fd px²)
FP_VARIANTS = [
    ("fp00",       0.0,    0),
    ("fp10",       1.0,    0),
    ("fp20",       2.0,    0),
    ("fp10_fd1k",  1.0, 1024),
]

VARIANTS_26 = []
for (name, base_overrides) in BASE_26:
    for (suffix, fp, fd) in FP_VARIANTS:
        VARIANTS_26.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_pm{int(round(PM_INH*100)):03d}_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": fp,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

# w=0 per step-25 finding
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
        variants=VARIANTS_26,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (fp=0)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Footprint factor (bootThresholdFactorFootprintPx) "
                        "sweep at sub4 carry. User observation: Sponza has "
                        "large cells that don't get refined. fp scales "
                        "trust threshold by fp*log2(cellPx) so big cells "
                        "demand more samples before trust, forcing finer-"
                        "level descent. Tests fp=1.0 (paper default), "
                        "fp=2.0 (aggressive), and fp+fd=1024 stack.")
_HEADLESS_SCRIPT_DONE = True
