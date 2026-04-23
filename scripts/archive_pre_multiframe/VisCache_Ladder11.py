"""
VisCache_Ladder11.py — Step 11: varThreshold × bootThreshold × footprintScale
sweep anchored on the step-10 multi-level winner.

Step 10's winner carry (qa012__th4) has a 1PL blob problem (81+ on x4) from
coarse-level RR over-trust at hard-shadow penumbrae. This step opens two
defenses against that over-trust:

  varThreshold (vt)  — tighten the RR variance gate so coarse cells don't
                        pass trust-check as easily. vt010 vs vt020.
  footprintScale (fp) — scale the trust floor by log2(cellPixels). Near-
                        camera large-footprint cells (where the artifact
                        pops) need more samples before trust kicks in.
                        fp0.0 (off, step-10 baseline) vs fp0.5.

Also re-sweep bootThreshold (th2 vs th4) since the interaction with vt+fp
isn't linear; the step-10 th4 carry may not remain the winner once the
variance gate tightens.

  2 vt × 2 th × 2 fp = 8 variants × 2 SPP = 16 runs/scene

Quant axis pinned to step-10 carry (qa012). Footprint=0 + vt010 mirrors
the step-10 baseline but with a tighter gate; footprint=0.5 + vt020
mirrors the paper's footprint-aware trust.

Usage:
    Mogwai.exe --headless -s scripts/VisCache_Ladder11.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    MULTI_LEVEL_SCENES, PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, \
    QUANT_SWEEP, SUBFRAME_2x2

STEP = "11"
res = int(os.environ.get("RES", "512"))

# run_ladder.py dispatches CHUNKS_PER_STEP["VisCache_Ladder11.py"] Mogwai
# processes per (step, scene), each setting CHUNK_IDX/CHUNK_COUNT. 48
# variants × 2 SPP = 96 runs/scene → 4 chunks of 24 runs keeps each
# process well under the OOM/GFX memory ceiling (~30 variants/process).
CHUNK_IDX   = int(os.environ.get("CHUNK_IDX",   "0"))
CHUNK_COUNT = int(os.environ.get("CHUNK_COUNT", "1"))

INHERITED_NAME = read_carried_winner("10")
if INHERITED_NAME is None:
    raise RuntimeError("[11] step 10 picks.json missing — run step 10 first.")
# qa-tag + matureThreshold not encoded in the standard tags, pinned here.
INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)  # bootThreshold

# Extract the qa tag for variant naming. Step 10's naming is qa<NN> (legacy
# all-lowercase) — reuse exactly as seen.
_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[11] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

# Sweep axes.
# Full vt range mirrors step 06 so single-level and multi-level responses
# are comparable. vt0 = 0.0001 sentinel ("trust only at variance = 0 modulo
# eps"); higher values loosen the RR gate.
VT_SWEEP  = {"vt0": 0.0001, "vt005": 0.05, "vt010": 0.10, "vt015": 0.15,
             "vt020": 0.20, "vt030": 0.30, "vt040": 0.40, "vt060": 0.60}
# Sample-count gate — `ct` (count) replaces the older `th` (threshold)
# naming to disambiguate from varThreshold / matureThreshold.
THR_SWEEP = {"ct2": 2, "ct4": 4}
# fp 0.5 was scrapped after step-11 v1 showed it destroys 32PL rays savings
# (95-98% rays) without improving 1PL blob. 0.1/0.2 are the milder probes.
FP_SWEEP  = {"fp0": 0.0, "fp01": 0.1, "fp02": 0.2}

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_11 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VARIANTS_ALL = []
for (name, base_overrides) in BASE_11:
    for vt_tag, vt_val in VT_SWEEP.items():
        for th_tag, th_val in THR_SWEEP.items():
            for fp_tag, fp_val in FP_SWEEP.items():
                tag = f"{th_tag}_{vt_tag}_{fp_tag}"
                VARIANTS_ALL.append((f"{name}__{tag}", {
                    **base_overrides,
                    **NO_JITTER,
                    "bootThreshold":  th_val,
                    "matureThreshold": 128,
                    "varThreshold":    vt_val,
                    "bootThresholdFactorFootprintPx":  fp_val,
                }))

# Contiguous chunking — each Mogwai process handles a slice of the variant
# list so per-process GPU memory stays below the empirical OOM ceiling.
_n = len(VARIANTS_ALL)
_chunk_size = (_n + CHUNK_COUNT - 1) // CHUNK_COUNT
_start = CHUNK_IDX * _chunk_size
_end   = min(_start + _chunk_size, _n)
VARIANTS_11 = VARIANTS_ALL[_start:_end]
print(f"[11] chunk {CHUNK_IDX+1}/{CHUNK_COUNT}: variants [{_start}:{_end}] "
      f"({len(VARIANTS_11)} of {_n})")

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

for scene_file in get_scenes(default=MULTI_LEVEL_SCENES):
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
        variants=VARIANTS_11,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# finalize on the last chunk only — earlier chunks leave partial CSV.
if CHUNK_IDX == CHUNK_COUNT - 1:
    # Manual carry (post-inspection, expanded sweep):
    #   - vt005 is the corner, NOT vt010. Expanded sweep (vt0..vt060 ×
    #     ct{2,4} × fp{0,0.1,0.2}) shows vt005 cuts 1PL blob from 26.7 (vt010)
    #     to 22.9 and 1AL blob from 25.1 to 17.4, all at matched 32PL rays
    #     (17.8%). Mirrors the single-level step-06 finding.
    #   - vt0 (0.0001) still over-tightens (1PL blob ~86 at ct4_vt0_fp0);
    #     coarse cascade cells read variance ≈ 0 spuriously.
    #   - fp0.1 gives no benefit at ct4_vt005 (identical metrics to fp0).
    #   - fp0.2 helps 1PL blob but triples 32PL rays — not worth it.
    #   - fp0.5 (tested in v1) destroys 32PL rays completely. Scrapped.
    CARRY_11 = f"{WINNER_NAME}__ct4_vt005_fp0"
    # Prune plot: 48 variants is too dense to read. Keep ct4 × fp0 only and
    # drop the loose-end vt plateau (vt030/vt040/vt060) — 5 variants left
    # (vt0, vt005, vt010, vt015, vt020). CSV keeps all 48 rows.
    _PLOT_VT_KEEP = {"vt0", "vt005", "vt010", "vt015", "vt020"}
    def _plot_filter(vname):
        toks = vname.split("__")[-1].split("_")
        return ("ct4" in toks and "fp0" in toks
                and any(t in _PLOT_VT_KEEP for t in toks))
    finalize_step(STEP, inherited_winners=[INHERITED_NAME],
                  carried_winners=[CARRY_11],
                  ref_step="10", ref_variant=INHERITED_NAME,
                  ref_label="multi-level step-10 carry",
                  variant_filter=_plot_filter)
    write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED_NAME],
                      carried={"pos": [CARRY_11]}, rule=_DEFAULT_PICKER_RULE,
                      notes="Manual carry: ct4_vt005_fp0. Expanded sweep "
                            "shows vt005 beats prior vt010 carry on every "
                            "blob metric (1PL 22.9 vs 26.7, 1AL 17.4 vs "
                            "25.1, 3AL 22.5 vs 23.8) at matched 32PL rays "
                            "(17.8%). fp0.1/0.2 mostly no-op or worse; "
                            "vt is the effective knob.")
_HEADLESS_SCRIPT_DONE = True
