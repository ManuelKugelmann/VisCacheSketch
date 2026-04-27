"""
VisCache_Ladder31.py — Step 31: N=32000 cascade + analytical entry + peek.

Design changes landing with this step:
  - numLevels bumped from 32 → 32000 (LEVELS_MULTI).
  - deriveFine uses a fixed total ratio (coarse/1024), independent of N.
    Previous coarse / pow(4, sqrt(N-1)) blew up at large N.
  - vhfLookup/vhfInsert compute startLvl analytically from per-pixel
    footprint: targetLvl from log(target/coarse)/log(fine/coarse)*(N-1),
    start = targetLvl - "2 doublings" (not 2 literal levels, since at
    N=32000 consecutive levels share quant indices).
  - Hierarchical consistency peek now peeks "1 doubling finer" instead of
    lvl+1 so the peek actually reads a different cell.

Matrix this step:
  a_fd0_hcOff       — no analytical entry, no peek           (baseline)
  b_fd4_hcOff       — target = 2×2 px, no peek
  c_fd16_hcOff      — target = 4×4 px, no peek
  d_fd64_hcOff      — target = 8×8 px, no peek
  e_fd0_hcOn        — no analytical entry, peek ON           (peek alone)
  f_fd4_hcOn        — target = 2×2 px + peek                 (full proposal)
  g_fd16_hcOn       — target = 4×4 px + peek
  h_fd64_hcOn       — target = 8×8 px + peek

8 variants × 3 spp × 7 scenes = 168 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "31"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[31] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[31] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

BASE_31 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, fd, hc)
VARIANTS = [
    ("a_fd0_hcOff",    0,  False),
    ("b_fd4_hcOff",    4,  False),
    ("c_fd16_hcOff",  16,  False),
    ("d_fd64_hcOff",  64,  False),
    ("e_fd0_hcOn",     0,  True),
    ("f_fd4_hcOn",     4,  True),
    ("g_fd16_hcOn",   16,  True),
    ("h_fd64_hcOn",   64,  True),
]

VARIANTS_31 = []
for (name, base_overrides) in BASE_31:
    for (suffix, fd, hc) in VARIANTS:
        VARIANTS_31.append((f"{name}__ct4_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": hc,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

# warmupFirst=2: 2 warmup frames (write-only, unmeasured) pre-fill cache
# so measurement frames benefit from a warm cache. Step-22 apples-to-apples.
MF_CONFIGS = [(2, 0, 1, 1),  (2, 0, 4, 1),  (2, 0, 16, 1)]

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
        variants=VARIANTS_31,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (fp=0)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="N=32000 cascade + analytical entry (target minus "
                        "2 doublings) + peek-1-doubling-finer hierarchical "
                        "consistency check. Entry restricts reads/writes to "
                        "~5-6 levels around per-pixel target; peek rejects "
                        "converged coarse cells whose finer cousin "
                        "disagrees (penumbra detector). Tests whether this "
                        "combination can kill the concentrated blob "
                        "artifacts without ballooning rays.")
_HEADLESS_SCRIPT_DONE = True
