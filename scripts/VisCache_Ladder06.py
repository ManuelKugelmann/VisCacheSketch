"""
VisCache_Ladder06.py — Step 06: varThreshold sweep at the step-05 winner.

Sweeps the RR variance gate — when cell variance drops below varThreshold
the RR decision trusts the cached μ; above it, the ray keeps tracing.
Raising varThreshold loosens that trust gate → more RR skips in high-
variance regions (especially shadow penumbrae on hard-light scenes, where
cells stay variance-heavy and the default 0.10 effectively forces full
tracing near edges).

Sweep values: {0.10, 0.20, 0.40} — 2× stepping at and above the default
0.10. Tag encodes the value ×100 zero-padded: vt010, vt020, vt040.

Step-05 winner baked in: pos_norm__pos + qA024_qB036 + th2.

  3 varThresh × 2 SPP = 6 runs/scene

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, write_picks_meta, pick_top_variants_per_bvariant, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "06"
res = int(os.environ.get("RES", "512"))

WINNER_QUANT_TAG = "qA024_qB036"
WINNER_QUANT = {"posACoarse": 0.24, "posBCoarse": 0.36}
WINNER_THRESH_TAG = "th2"
WINNER_THRESH = {"bootThreshold": 2, "matureThreshold": 128}
NORMAL_A = 60.0

WINNER_NAME = f"pos_norm__pos__{WINNER_QUANT_TAG}__{WINNER_THRESH_TAG}"
WINNER_BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    **WINNER_QUANT,
    **WINNER_THRESH,
}

VAR_THRESH_VALUES = [0.10, 0.20, 0.40]

def _vt_tag(v): return f"vt{int(round(v * 100)):03d}"

VARIANTS_06 = [
    (f"{WINNER_NAME}__{_vt_tag(vt)}",
     {**WINNER_BASE, "varThreshold": vt})
    for vt in VAR_THRESH_VALUES
]

STEP_OVERRIDES = {**RR_ADAPTIVE, **SUBFRAME_2x2}

for scene_file in get_scenes():
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
        variants=VARIANTS_06,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[WINNER_NAME])
_carried_06 = pick_top_variants_per_bvariant(STEP, n_top=1, spp=1)
write_picks_meta(STEP, inherited_from="05", inherited=[WINNER_NAME],
                  carried=_carried_06, rule=_DEFAULT_PICKER_RULE,
                  notes="varThreshold sweep — how much variance can a cell "
                        "carry and still be trusted via RR? Target: reduce "
                        "rays in 1-point-light shadow penumbra without "
                        "degrading err/blob above median+25%.")
_HEADLESS_SCRIPT_DONE = True
