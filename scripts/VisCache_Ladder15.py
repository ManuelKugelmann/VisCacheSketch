"""
VisCache_Ladder15.py — Step 15: stderr gate + hierarchical check + accel decay
(MULTI-LEVEL, step-11 carry lineage).

Multi-level mirror of step 13. Same 3-axis sweep (se × hc × ad) on the
step-11 cascade baseline (qa012 + ct4 + vt005 + fp0, multi-level). Target:
show whether stderr + hierarchical defend the 1PL x4 AND x16 blob that
step 12 couldn't fix.

  4 se × 2 hc × 2 ad = 16 variants × 3 SPP (x1/x4/x16) = 48 runs/scene
  × 4 scenes = 192 runs. Chunked 2× to stay under GPU memory ceiling.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 15
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    ALL_SCENES, PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

# 7-scene superset — Cornell suite (blob/penumbra stress) + the big
# geometry scenes Bistro/Sponza (real-world stress, more pressure on the
# hash table). When invoked without -c, step 15 runs the full set so
# single-light Cornell findings can be cross-checked against scenes with
# complex occluders and soft indirect lighting.
BIG_SCENES_15 = list(ALL_SCENES) + [
    "BistroInterior.pyscene",
    "BistroExterior.pyscene",
    "Sponza.pyscene",
]

STEP = "15"
res = int(os.environ.get("RES", "512"))

CHUNK_IDX   = int(os.environ.get("CHUNK_IDX",   "0"))
CHUNK_COUNT = int(os.environ.get("CHUNK_COUNT", "1"))

INHERITED_NAME = read_carried_winner("11")
if INHERITED_NAME is None:
    raise RuntimeError("[15] step 11 picks.json missing — run step 11 first.")

# Extract qa tag (same as step 11).
_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[15] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

# Inherit step-11 params (ct4, vt005, fp0).
INHERITED = parse_variant_tags(INHERITED_NAME)

SE_SWEEP = {"se05": 0.05, "se10": 0.10, "se15": 0.15, "se20": 0.20}
HC_SWEEP = {"hc0": False, "hc1": True}
AD_SWEEP = {"ad0": 0.0, "ad50": 0.5}

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_15 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VARIANTS_ALL = []
for (name, base_overrides) in BASE_15:
    for se_tag, se_val in SE_SWEEP.items():
        for hc_tag, hc_val in HC_SWEEP.items():
            for ad_tag, ad_val in AD_SWEEP.items():
                tag = f"{se_tag}_{hc_tag}_{ad_tag}"
                VARIANTS_ALL.append((f"{name}__ct4_vt005_fp0__{tag}", {
                    **base_overrides,
                    **NO_JITTER,
                    "bootThreshold":                 4,
                    "matureThreshold":               128,
                    "varThreshold":                  0.05,
                    "bootThresholdFactorFootprintPx": 0.0,
                    "stderrThreshold":               se_val,
                    "enableHierarchicalConsistency": hc_val,
                    "accelDecayDisagreeThresh":      ad_val,
                }))

# Contiguous chunking — 16 variants × 3 SPP = 48 runs; 2 chunks of 24 keeps
# us well under the GPU OOM ceiling seen in step 11.
_n = len(VARIANTS_ALL)
_chunk_size = (_n + CHUNK_COUNT - 1) // CHUNK_COUNT
_start = CHUNK_IDX * _chunk_size
_end   = min(_start + _chunk_size, _n)
VARIANTS_15 = VARIANTS_ALL[_start:_end]
print(f"[15] chunk {CHUNK_IDX+1}/{CHUNK_COUNT}: variants [{_start}:{_end}] "
      f"({len(VARIANTS_15)} of {_n})")

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

for scene_file in get_scenes(default=BIG_SCENES_15):
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
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4), (1, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_15,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

if CHUNK_IDX == CHUNK_COUNT - 1:
    finalize_step(STEP, inherited_winners=[INHERITED_NAME],
                  ref_step="11", ref_variant=INHERITED_NAME,
                  ref_label="step-11 multi-level carry")
    write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED_NAME],
                      carried={}, rule=_DEFAULT_PICKER_RULE,
                      notes="stderr × hierarchical × accel-decay sweep on "
                            "step-11 multi-level carry. Targets the x16 1PL "
                            "regression step 12 couldn't fix. Carry set "
                            "post-inspection.")
_HEADLESS_SCRIPT_DONE = True
