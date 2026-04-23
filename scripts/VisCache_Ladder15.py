"""
VisCache_Ladder15.py — Step 15: Sponza bias attack under multi-frame.

Step 27 revealed the most important open problem: under multi-frame,
Sponza x4 err goes from +0.17% (single-frame, artifactual parity) to
+14.8% — the cache actively HURTS Sponza when properly sampled. 1PL
similarly regresses. Step 11 (pMin sweep) shows pMin doesn't defend
bias under multi-frame — different problem than single-frame era.

Hypothesis: Sponza's directional sun creates large spatial regions
of coherent low-visibility cells. Under multi-frame, many Bayer
slots contribute over 4-16 frames, cells mature quickly, and the
mean μ reflects the COARSE cell average (μ ≈ 0.6 in a half-shadowed
region) — which is systematically wrong for individual pixels.

Defenses to combine in a targeted sweep:
  1. HIGH ct (32, 64) — more samples before trust; forces finer-level
     descent at mature cells
  2. TIGHT vt (0.01, 0.003) — only trust cells with μ near 0 or 1
  3. fd=1024 lookup+insert-skip — refuse big cells entirely, force
     fine-level resolution
  4. pm020 — high forced-trace rate for corrective samples

Six targeted variants (Sponza-regime focused):
  A: ct=16, vt=0.03, fd=0, pm=0.05   — step-23 equivalent (baseline)
  B: ct=16, vt=0.01, fd=0, pm=0.10   — step-25 equivalent
  C: ct=32, vt=0.01, fd=0, pm=0.10   — higher ct floor
  D: ct=16, vt=0.01, fd=1024, pm=0.10 — force-descend big cells
  E: ct=32, vt=0.003, fd=1024, pm=0.20 — maximum defense
  F: ct=16, vt=0.03, fd=0, pm=0.20   — pm-alone defense

6 × 6 × 7 = 252 runs. Large but focused — these are the realistic
candidates for Sponza-safe carry.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 15
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "15"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("13")
if INHERITED_NAME is None:
    # Fallback: inherit from step 10 if 13 missing
    INHERITED_NAME = read_carried_winner("10")
if INHERITED_NAME is None:
    raise RuntimeError("[15] need step 13 or step 10 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[15] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_15 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# Each tuple: (tag_suffix, ct, vt, fd_px, pm)
BIAS_DEFENSE_VARIANTS = [
    ("A_ct16_vt003_fd0_pm005",   16,  0.03,    0, 0.05),
    ("B_ct16_vt001_fd0_pm010",   16,  0.01,    0, 0.10),
    ("C_ct32_vt001_fd0_pm010",   32,  0.01,    0, 0.10),
    ("D_ct16_vt001_fd1k_pm010",  16,  0.01, 1024, 0.10),
    ("E_ct32_vt003m_fd1k_pm020", 32,  0.003, 1024, 0.20),
    ("F_ct16_vt003_fd0_pm020",   16,  0.03,    0, 0.20),
]

VARIANTS_15 = []
for (name, base_overrides) in BASE_15:
    for (suffix, ct, vt, fd, pm) in BIAS_DEFENSE_VARIANTS:
        VARIANTS_15.append((f"{name}__{suffix}", {
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
        variants=VARIANTS_15,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="13", ref_variant=INHERITED_NAME,
              ref_label="step-13 carry")
write_picks_meta(STEP, inherited_from="13", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Sponza bias attack under multi-frame. Combines "
                        "high ct (32), tight vt (0.003-0.01), fd=1024 "
                        "force-descend + insert-skip, and pm020 rate-"
                        "defense. 6 targeted variants. Winner must pass "
                        "the per-scene outlier gate (no scene catastrophic).")
_HEADLESS_SCRIPT_DONE = True
