"""
VisCache_Ladder05.py — Step 05: quant × threshold sweep, pos__pos.

Sweeps step 03's top-3 pos quantAB winners against 3 boot thresholds.
Candidates resolve dynamically from step 03's current picker output so the
single source of truth for "best quants" is pick_top_variants_per_bvariant
in LadderCommon — no hardcoded constants to drift out of sync.

footprintScale stays at 0 (removed from single-level steps; multi-level
from step 10 takes over cell-size modulation).

  3 quantAB × 3 thresh × 2 SPP = 18 runs/scene

Fallback: if step 03 CSV is missing, use a diagonal placeholder so the
script still runs in isolation (emits a warning).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder05.py
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, pick_top_variants_per_bvariant, write_picks_meta, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "05"
res = int(os.environ.get("RES", "512"))

# Resolve 3 quantAB candidates from step 03's pos branch picker.
_picks_03 = pick_top_variants_per_bvariant("03", n_top=3, spp=1)
_pos_picks = _picks_03.get("pos", [])

def _parse_pos_pick(name):
    """'pos_norm__pos__qA024_qB036' → ('qA024_qB036', qA=0.24, qB=0.36)."""
    m = re.search(r"qA(\d+)_qB(\d+)$", name)
    if not m:
        return None
    qA = int(m.group(1)) / 100.0
    qB = int(m.group(2)) / 100.0
    return (f"qA{m.group(1)}_qB{m.group(2)}", qA, qB)

QUANT_CANDIDATES = []
for n in _pos_picks[:3]:
    parsed = _parse_pos_pick(n)
    if parsed is None:
        continue
    tag, qA, qB = parsed
    QUANT_CANDIDATES.append((tag, {"posACoarse": qA, "posBCoarse": qB}))

if not QUANT_CANDIDATES:
    print("[05] WARNING: step-03 CSV missing or no pos picks — falling back "
          "to diagonal placeholder {qA006_qB018, qA012_qB036, qA024_qB072}.")
    QUANT_CANDIDATES = [
        ("qA006_qB018", {"posACoarse": 0.06, "posBCoarse": 0.18}),
        ("qA012_qB036", {"posACoarse": 0.12, "posBCoarse": 0.36}),
        ("qA024_qB072", {"posACoarse": 0.24, "posBCoarse": 0.72}),
    ]

print(f"[05] Inherited quantAB candidates from step 03: "
      f"{[t for t, _ in QUANT_CANDIDATES]}")

# Boot threshold sweep. Tag encodes actual boot value. Mature fixed at 128.
# th1 = trust the cache immediately after first sample (no boot gate). th0
# would mean "trust even with zero samples" — that's a pure guess/default
# mu=0.5 estimate, not a cache read, so we start the sweep at 1 rather
# than 0.
THRESH_SWEEP = [
    ("th1", {"bootThreshold": 1, "matureThreshold": 128}),
    ("th2", {"bootThreshold": 2, "matureThreshold": 128}),
    ("th4", {"bootThreshold": 4, "matureThreshold": 128}),
    ("th8", {"bootThreshold": 8, "matureThreshold": 128}),
]

NORMAL_A = 60.0

POS_BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
}

VARIANTS_05 = []
for (qtag, qovr) in QUANT_CANDIDATES:
    for (ttag, tovr) in THRESH_SWEEP:
        VARIANTS_05.append((
            f"pos_norm__pos__{qtag}__{ttag}",
            {**POS_BASE, **qovr, **tovr},
        ))

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
        variants=VARIANTS_05,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# Resolve step-05's carry-forward from its own picker — step 06 will pick
# this up via its inherited_winners list.
_picks_05 = pick_top_variants_per_bvariant(STEP, n_top=1, spp=1)
_carry_05 = [v for vs in _picks_05.values() for v in vs]

_inherited_05 = [f"pos_norm__pos__{t}" for t, _ in QUANT_CANDIDATES]
finalize_step(STEP,
              inherited_winners=_inherited_05,
              carried_winners=_carry_05)
write_picks_meta(STEP,
                  inherited_from="03",
                  inherited=_inherited_05,
                  carried=_picks_05,
                  rule=_DEFAULT_PICKER_RULE)
_HEADLESS_SCRIPT_DONE = True
