"""
VisCache_Ladder06.py — Step 06: varThreshold sweep at the step-05 winner.

Sweeps the RR variance gate — when cell variance drops below varThreshold
the RR decision trusts the cached μ; above it, the ray keeps tracing.
Raising varThreshold loosens that trust gate → more RR skips in high-
variance regions (especially shadow penumbrae on hard-light scenes, where
cells stay variance-heavy and the default 0.10 effectively forces full
tracing near edges).

Sweep values: {0.0001, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60}. Dense around
the default 0.10 sweet spot, with `vt0` (0.0001) as the "trust only if
variance = 0 modulo eps" extreme probe — mirrors the step 11 vt0 run so
single-level and multi-level behaviour at that extreme are comparable.
Tag: `vt0` for 0.0001, `vt<value×100 pad-3>` otherwise (vt005, vt010, …).

Step-05 winner inherited via read_carried_winner("05") → parse_variant_tags.

  8 varThresh × 2 SPP = 16 runs/scene

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, write_picks_meta, pick_top_variants_per_bvariant, \
    read_carried_winner, parse_variant_tags, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "06"
res = int(os.environ.get("RES", "512"))

WINNER_NAME = read_carried_winner("05")
if WINNER_NAME is None:
    raise RuntimeError("[06] step 05 picks.json missing — run step 05 first.")
WINNER_OVERRIDES = parse_variant_tags(WINNER_NAME)
NORMAL_A = 60.0

WINNER_BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    "matureThreshold": 128,
    **WINNER_OVERRIDES,
}

VAR_THRESH_VALUES = [0.0001, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60]

def _vt_tag(v):
    # `vt0` = 0.0001: semantic "trust only if variance = 0 modulo eps".
    # Matches the step-11 convention; the numeric parser in LadderCommon
    # maps vt0 → 0.0001 (sentinel) to avoid the shader collapsing to 0.0.
    if v <= 0.005:
        return "vt0"
    return f"vt{int(round(v * 100)):03d}"

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

finalize_step(STEP, inherited_winners=[WINNER_NAME],
              ref_step="05", ref_variant=WINNER_NAME,
              ref_label="step-05 carry (pre-varThreshold)")
_carried_06 = pick_top_variants_per_bvariant(STEP, n_top=1, spp=1)
write_picks_meta(STEP, inherited_from="05", inherited=[WINNER_NAME],
                  carried=_carried_06, rule=_DEFAULT_PICKER_RULE,
                  notes="varThreshold sweep — how much variance can a cell "
                        "carry and still be trusted via RR? Target: reduce "
                        "rays in 1-point-light shadow penumbra without "
                        "degrading err/blob above median+25%.")
_HEADLESS_SCRIPT_DONE = True
