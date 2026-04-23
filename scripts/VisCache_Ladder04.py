"""
VisCache_Ladder04.py — Step 04: SPP convergence for step-03 top-3 per B-variant.

Reads step 03's stats CSV, picks the top-3 variants per B-variant (pos /
dir_dist1 / dir_dist) by mean composite score at x1 SPP, then re-renders
each at x1 / x4 / x16 SPP. Validates that step-03's winners stay good as
SPP grows (no pathological convergence).

  3 B-variants × 3 top-3 quant × 3 SPP = 27 runs/scene

Placeholder behavior if step 03 CSV is missing: falls back to the diagonal
(qA006_qB018, qA012_qB036, qA024_qB072) for pos__pos only, emitting a
warning — so a cold ladder run still produces something, but the sweep
becomes degenerate (1 B-variant × 3 candidates × 3 SPP = 9 runs).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder04.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, pick_top_variants_per_bvariant, write_picks_meta, \
    _DEFAULT_PICKER_RULE, build_per_axis_quant_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "04"
res = int(os.environ.get("RES", "512"))

CHUNK_IDX   = int(os.environ.get("CHUNK_IDX",   "0"))
CHUNK_COUNT = int(os.environ.get("CHUNK_COUNT", "1"))

# Resolve step-03 top-3 per B-variant into full override dicts via the
# shared 45-variant builder.
ALL_03 = dict(build_per_axis_quant_variants(PRESET_MINIMAL))
picks = pick_top_variants_per_bvariant("03", n_top=3, spp=1)

winner_names = [n for vs in picks.values() for n in vs]
if not winner_names:
    print("[04] WARNING: step-03 CSV missing or empty — falling back to diagonal "
          "pos__pos candidates. Run step 03 first for the real sweep.")
    winner_names = ["pos_norm__pos__qA006_qB018",
                    "pos_norm__pos__qA012_qB036",
                    "pos_norm__pos__qA024_qB072"]

VARIANTS_ALL_04 = [(n, ALL_03[n]) for n in winner_names if n in ALL_03]

# Contiguous chunking — each Mogwai process handles a slice of the variant
# list so per-process ray/capture/Mogwai-memory stays below the empirical
# crash ceiling (~22 variants × 3 SPP triggered the access violation).
_n = len(VARIANTS_ALL_04)
_chunk_size = (_n + CHUNK_COUNT - 1) // CHUNK_COUNT
_start = CHUNK_IDX * _chunk_size
_end   = min(_start + _chunk_size, _n)
VARIANTS_04 = VARIANTS_ALL_04[_start:_end]

print(f"[04] chunk {CHUNK_IDX+1}/{CHUNK_COUNT}: variants [{_start}:{_end}] "
      f"({len(VARIANTS_04)} of {_n})")

# Summary log: which B-variants contributed, how many winners each.
for bv, names in picks.items():
    print(f"[04] B-variant {bv}: {len(names)} winner(s) — {', '.join(names)}")

STEP_OVERRIDES = {**RR_ADAPTIVE, **SUBFRAME_2x2}

for scene_file in get_scenes():
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
        frame_configs=[(1, 0, 1, 1), (1, 0, 4, 1), (1, 0, 16, 1)],
        scene_file=scene_file,
        variants=VARIANTS_04,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# Finalize only on last chunk — earlier chunks leave partial CSV.
if CHUNK_IDX == CHUNK_COUNT - 1:
    finalize_step(STEP, inherited_winners=winner_names, carried_winners=[])
    _carried_04 = pick_top_variants_per_bvariant(STEP, n_top=3, spp=1)
    write_picks_meta(STEP, inherited_from="03", inherited=winner_names,
                      carried=_carried_04, rule=_DEFAULT_PICKER_RULE,
                      notes="SPP convergence for step-03 top-3 per B-variant.")
_HEADLESS_SCRIPT_DONE = True
