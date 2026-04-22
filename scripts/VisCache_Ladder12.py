"""
VisCache_Ladder12.py — Step 12: bootThreshold (ct) sweep on step-11 carry.

Step 11 surfaced `qa012__ct4_vt005_fp0` as the multi-level carry. 1PL x4
blob is still 22.9 — better than pre-vt-tightening, but worth pushing
further. This step tests whether a higher sample-count gate (ct) reduces
1PL blob at the expected rays cost. Bigger near-camera cells (the ones
that straddle the penumbra) mature more slowly with higher ct → more
rays traced against them → fewer spurious "variance ≈ 0 after 2 samples"
trust decisions.

Fixed axes (from step-11 carry): qa012, vt005, fp0, multi-level, no jitter.

Three axes swept:
  - ct ∈ {2, 4, 8, 16, 32}. ct2 kept as the step-10 baseline reference;
    ct4 is the current carry; ct8/16/32 probe whether a stricter sample
    gate defends 1PL penumbra at rays cost.
  - warmup_first ∈ {1, 2}. w=2 dedicates half the 2×2 Bayer cycle
    write-only before any query, spreading samples over more pixels per
    cell before first mature-time query.
  - forceDescendFootprintPx ∈ {0, 1024}. NEW shader knob (this step):
    when a cell's screen-space footprint exceeds the threshold,
    vhfLookup refuses the convergence early-stop and always descends
    to refine. fd=0 = off (legacy). fd=1024 (32×32 px) triggers on most
    near-camera cells — the exact regime where 1PL blob lives.

  5 ct × 2 warmup × 2 fd = 20 variants × 2 SPP = 40 runs/scene × 4
  scenes = 160 runs. Single-chunk fits under the GPU memory ceiling.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 12
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "12"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("11")
if INHERITED_NAME is None:
    raise RuntimeError("[12] step 11 picks.json missing — run step 11 first.")

# Extract the qa tag (same convention as step 11).
_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[12] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

# Step 11 carry params → pin vt and fp, sweep ct.
INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
VT_VAL = INHERITED_TAGS.get("varThreshold", 0.05)
FP_VAL = 0.0  # step-11 winner has fp=0; fp axis parked.

CT_SWEEP = {"ct2": 2, "ct4": 4, "ct8": 8, "ct16": 16, "ct32": 32}
# forceDescendFootprintPx: 0 = off (legacy early-stop on convergence).
# 1024 (32×32 pixels) triggers descent on most near-camera cells on a
# 512² viewport — the exact regime where 1PL penumbra blob lives.
FD_SWEEP = {"fd0": 0, "fd1k": 1024}

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_12 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

def _vt_tag(v):
    return "vt0" if v <= 0.005 else f"vt{int(round(v * 100)):03d}"

_VT_TAG = _vt_tag(VT_VAL)

VARIANTS_12 = []
for (name, base_overrides) in BASE_12:
    for ct_tag, ct_val in CT_SWEEP.items():
        for fd_tag, fd_val in FD_SWEEP.items():
            tag = f"{ct_tag}_{_VT_TAG}_fp0_{fd_tag}"
            VARIANTS_12.append((f"{name}__{tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":   ct_val,
                "matureThreshold": 128,
                "varThreshold":    VT_VAL,
                "bootThresholdFactorFootprintPx":  FP_VAL,
                "forceDescendFootprintPx": fd_val,
            }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4],
        mogwai_globals=globals(),
    )

    # warmup_first ∈ {1, 2}: the first N subframes of each Bayer cycle are
    # write-only. w=2 doubles pre-query write dispersion relative to the
    # current w=1 baseline. Row-keyed by (variant, spp, warmup_first) so
    # w=1 and w=2 land as separate CSV rows under the same variant name.
    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4), (1, 0, 1, 16),
                       (2, 0, 1, 1), (2, 0, 1, 4), (2, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_12,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# Carry deferred — the rays / 1PL-blob tradeoff is a judgment call; set
# carry post-inspection via a manual write_picks_meta override.
finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="11", ref_variant=INHERITED_NAME,
              ref_label="step-11 carry")
write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="ct sweep on step-11 carry (qa012, vt005, fp0). "
                        "Target: reduce 1PL blob (22.9 at ct4) by raising "
                        "sample-count gate so big near-camera cells mature "
                        "more slowly. Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True
