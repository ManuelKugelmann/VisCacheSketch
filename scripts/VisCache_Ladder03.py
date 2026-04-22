"""
VisCache_Ladder03.py — Step 03: per-axis quantization sweep (all variants).

Logically one step containing all variants:
  pos_norm__pos         qA × qB            = 4 × 4 = 16
  pos_norm__dir_dist1   qA × qD_FINE       = 4 × 4 = 16   (distB collapsed)
  pos_norm__dir_dist    qA × qD × qd       = 4 × 3 × 3 = 36  (wider qD/qd steps)
                                             --
                                             68 × 2 SPP = 136 runs/scene

Runs split across multiple Mogwai processes (CHUNK_COUNT chunks) to stay
under the per-process OOM ceiling. All chunks share the same step-03 CSV
and capture dir; resume in run_variants skips keys already in the CSV.
finalize_step (plots) runs on the last chunk only.

Axes:
  qA (posA)  ∈ {0.06, 0.12, 0.24, 0.48}   tag qA<posA×100>
  qB (posB)  ∈ {0.18, 0.36, 0.72, 1.44}   tag qB<posB×100>
  qD (dirB)  ∈ {8°, 30°, 60°}              tag qD<deg,pad2>   (dir_dist only — dir_dist1 keeps 4 values)
  qd (distB) ∈ {0.24, 0.96, 1.92}         tag qd<distB×100>  (dir_dist only)

Env vars (set by run_ladder.py):
  CHUNK_IDX     0-based chunk index (default 0)
  CHUNK_COUNT   total chunks (default 1 — no chunking)

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder03.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, plot_overviews_per_bvariant, plot_top3_comparison, \
    copy_summary_to_root, pick_top_variants_per_bvariant, write_picks_meta, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "03"
res = int(os.environ.get("RES", "512"))

CHUNK_IDX   = int(os.environ.get("CHUNK_IDX",   "0"))
CHUNK_COUNT = int(os.environ.get("CHUNK_COUNT", "1"))

QA_VALUES      = [0.06, 0.12, 0.24, 0.48]
QB_VALUES      = [0.18, 0.36, 0.72, 1.44]
# dir_dist1 (distB collapsed) keeps the dense 4-value qD sweep; dir_dist
# (qA × qD × qd) uses a wider 3-value qD/qd sweep to keep variant count
# manageable (4×3×3=36 instead of 4×4×4=64).
QD_VALUES_FINE = [8.0, 15.0, 30.0, 60.0]
QD_VALUES      = [8.0, 30.0, 60.0]
QD_DIST_VALUES = [0.24, 0.96, 1.92]

def _qA(v): return f"qA{int(round(v * 100)):03d}"
def _qB(v): return f"qB{int(round(v * 100)):03d}"
def _qD(v): return f"qD{int(round(v)):02d}"
def _qd(v): return f"qd{int(round(v * 100)):03d}"

NORMAL_A = 60.0

VARIANTS_ALL = []

for qA in QA_VALUES:
    for qB in QB_VALUES:
        tag = f"{_qA(qA)}_{_qB(qB)}"
        VARIANTS_ALL.append((f"pos_norm__pos__{tag}", {
            **PRESET_MINIMAL,
            "enableVisCacheDirDistAddr": False,
            "enableVisCacheNormalAddr": True,
            "posACoarse": qA,
            "normalACoarse": NORMAL_A,
            "posBCoarse": qB,
        }))

for qA in QA_VALUES:
    for qD in QD_VALUES_FINE:
        tag = f"{_qA(qA)}_{_qD(qD)}"
        VARIANTS_ALL.append((f"pos_norm__dir_dist1__{tag}", {
            **PRESET_MINIMAL,
            "enableVisCacheDirDistAddr": True,
            "enableVisCacheNormalAddr": True,
            "posACoarse": qA,
            "normalACoarse": NORMAL_A,
            "dirBCoarse": qD,
            "distBCoarse": 1000.0,
        }))

for qA in QA_VALUES:
    for qD in QD_VALUES:
        for qd in QD_DIST_VALUES:
            tag = f"{_qA(qA)}_{_qD(qD)}_{_qd(qd)}"
            VARIANTS_ALL.append((f"pos_norm__dir_dist__{tag}", {
                **PRESET_MINIMAL,
                "enableVisCacheDirDistAddr": True,
                "enableVisCacheNormalAddr": True,
                "posACoarse": qA,
                "normalACoarse": NORMAL_A,
                "dirBCoarse": qD,
                "distBCoarse": qd,
            }))

# Contiguous chunking — slice matches a run-ladder chunk plan cleanly and keeps
# related variants adjacent (easier to reason about mid-run state).
n = len(VARIANTS_ALL)
chunk_size = (n + CHUNK_COUNT - 1) // CHUNK_COUNT
start = CHUNK_IDX * chunk_size
end   = min(start + chunk_size, n)
VARIANTS_03 = VARIANTS_ALL[start:end]

print(f"[03] chunk {CHUNK_IDX+1}/{CHUNK_COUNT}: variants [{start}:{end}] "
      f"({len(VARIANTS_03)} of {n})")

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
        variants=VARIANTS_03,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# Plot only after the final chunk — earlier chunks leave partial CSV. Step
# 03 skips the combined overview (too crowded at 45 variants) and produces
# only the per-variant subsets + the top-3 comparison.
if CHUNK_IDX == CHUNK_COUNT - 1:
    # Plot subset for dir_dist: trim to 3×2×2 = 12 so the legend stays
    # readable. Drops the tails (qA048 aggressive, qD08 fine, qd024 fine);
    # keeps the current top-1 winner qA012_qD60_qd192. CSV / sweep are
    # untouched — this filter affects plotting only. Non-dir_dist rows
    # (pos, dir_dist1) pass through unfiltered; plot_overviews_per_bvariant
    # applies this callable within each B-variant grouping.
    QA_PLOT       = [0.06, 0.12, 0.24]
    QD_PLOT       = [30.0, 60.0]
    QD_DIST_PLOT  = [0.96, 1.92]
    _qA_tags = {f"_{_qA(v)}_" for v in QA_PLOT}
    _qD_tags = {f"_{_qD(v)}_" for v in QD_PLOT}
    _qd_tags = {f"_{_qd(v)}"  for v in QD_DIST_PLOT}
    def _variant_ok(name):
        if "__dir_dist__" not in name:
            return True
        return (any(t in name for t in _qA_tags)
                and any(t in name for t in _qD_tags)
                and any(name.endswith(t) for t in _qd_tags))
    plot_overviews_per_bvariant(STEP, variant_filter=_variant_ok)
    plot_top3_comparison(STEP, n_top=3)
    finalize_step(STEP, skip_overview=True)
    _carried_03 = pick_top_variants_per_bvariant(STEP, n_top=3, spp=1)
    write_picks_meta(STEP, carried=_carried_03, rule=_DEFAULT_PICKER_RULE,
                      notes="Step 03 is start-of-ladder for per-axis quant; no inherited.")
_HEADLESS_SCRIPT_DONE = True
