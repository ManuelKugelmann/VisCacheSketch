"""
VisCache_Ladder29.py — Step 29: targeted artifact killers at low-trace baseline.

Step 26 showed huge rays savings at fp00 (1PL x4: 4% rays, Sponza x4: 15%
rays) with concentrated blob artifacts (54 on 1PL, 146 on Sponza).
fp>=1 eliminates blob but floods rays to 95-100% (near vanilla). Step 29
tries light mechanisms that already exist in the shader and might reject
only the bad cells without slashing the cache everywhere.

Keeps fp=0 baseline (low rays). Adds one gate at a time:

  a_baseline      — fp00 (step-18 sub4 carry, no extra gate)
  b_vt0005        — vt=0.005 (very tight convergence — any disagreement descends)
  c_stderr005     — stderrThreshold=0.05 (principled Bernoulli N-aware gate)
  d_stderr01      — stderrThreshold=0.10 (looser stderr)
  e_fd16          — fd=16 (force-descend until cell ≤ 4×4 px)
  f_fd64          — fd=64 (force-descend until ≤ 8×8 px)
  g_hc            — hierarchical consistency ON (peek finer level μ)
  h_vt0005_fd64   — stack tightest vt with fd64

8 variants × 3 spp × 7 scenes = 168 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "29"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[29] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[29] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

PM_INH = 0.05

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_29 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, vt, stderr, fd, hc)
VARIANTS = [
    ("a_baseline",     0.01, 0.00,    0, False),
    ("b_vt0005",       0.005, 0.00,   0, False),
    ("c_stderr005",    0.01, 0.05,    0, False),
    ("d_stderr01",     0.01, 0.10,    0, False),
    ("e_fd16",         0.01, 0.00,   16, False),
    ("f_fd64",         0.01, 0.00,   64, False),
    ("g_hc",           0.01, 0.00,    0, True),
    ("h_vt0005_fd64",  0.005, 0.00,  64, False),
]

VARIANTS_29 = []
for (name, base_overrides) in BASE_29:
    for (suffix, vt, se, fd, hc) in VARIANTS:
        VARIANTS_29.append((f"{name}__ct4_fp0_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  vt,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               se,
            "enableHierarchicalConsistency": hc,
            "hierarchicalMuTolerance":       0.20,
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
        variants=VARIANTS_29,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (fp0)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Targeted artifact killers at low-trace fp00 baseline. "
                        "Tests whether existing shader gates (vt, stderr, fd, "
                        "hc) can identify the ~3-5% boundary cells causing "
                        "concentrated blob artifacts while keeping fp00's 10-"
                        "20% rays cost. Target: blob < 10 and err < 1% on "
                        "every scene with rays <= 30%.")
_HEADLESS_SCRIPT_DONE = True
