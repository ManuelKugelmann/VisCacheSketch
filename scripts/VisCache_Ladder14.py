"""
VisCache_Ladder14.py - Step 14: fd × ct sweep [CANONICAL WINNER FINDER].

STATUS: This is the canonical sweep that produced the final per-SPP optima.
Per-SPP winners (cross-scene-averaged, no scene with art regression > 1pp):
  x1  → cell16x16 ct=32   (15% rays saved across 4 scenes; -2.4pp art max)
  x4  → cell8x8   ct=8    (31% saved; -1.2pp art max)
  x16 → cell8x8   ct=8    (50% saved;  +0.8pp art max)
Universal SPP-invariant safe config: cell4x4 ct=4 (works at all SPPs;
max -5pp art regression on clean 1PointLight x1).

Step 13 found cell4x4 (fd=16) ct=16 saves 80% rays at x16 SPP but
nothing at x1 SPP — cells don't mature in 1 frame. cell4x4 only
sees 4 samples/frame at SPP=1 (16 pixels in cell, 1 of 4 bayer slots
active per frame), so ct=4 floor with 12% Bernoulli false-trust on
penumbra cells.

Larger cells mature faster:
  cell4x4   (fd=16):    4 samples/frame  @ SPP=1 → ct=4   floor (false-trust 12%)
  cell8x8   (fd=64):   16 samples/frame  @ SPP=1 → ct=16  floor (false-trust <0.01%)
  cell16x16 (fd=256):  64 samples/frame  @ SPP=1 → ct=64  floor (false-trust ~1e-19)
  cell32x32 (fd=1024): 256 samples/frame @ SPP=1 → ct=256 floor (false-trust 0)

Trade-off: larger cells average over more screen area, so they blur
the cached visibility. For hard-shadow regions (μ=0 or μ=1) the
blur is harmless because the region is uniformly 0 or uniformly 1.
For penumbra-edge cells the average is wrong-by-aggregation, but
vt=0.01 still rejects them via Bernoulli variance.

Sweep: fd ∈ {16, 64, 256, 1024} × ct ∈ {ct_floor, 2×ct_floor}
where ct_floor = fd/4 (samples per cell per frame at SPP=1, bayer 2×2).
= 4 × 2 = 8 variants × 3 SPP × 4 scenes = 96 runs.
Scenes: 1PointLight + 32PointLights (Cornell hard-shadow) + BistroInterior
+ Sponza (real-scene complexity, many lights, large penumbra regions).

Goal: find the cell size + ct combo that saves rays at x1 SPP without
artifacts. Hard-shadow scenes only; area-light scenes saturate.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "14"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("10")
if INHERITED is None:
    raise RuntimeError("[14] step 10 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
BAYER_N = 2
# Fixed at step-13 winner regime: vt and pm settled.
# vt: Bernoulli theorem makes all vt ∈ [0.01, 0.08] equivalent (rejects all
# penumbra). vt=0.03 mid-bucket, no benefit to sweep tighter or looser.
# pm: 0.02 beat 0.10 in step 13 by ~3× more savings, no artifact penalty.
VT = 0.03
PM = 0.02

# fd → cell_n (cells_n × cells_n pixels = fd):
#   16   → cell4x4   (ct floor=4   at SPP=1)
#   64   → cell8x8   (ct floor=16)
#   256  → cell16x16 (ct floor=64)
#   1024 → cell32x32 (ct floor=256)
FD_VALUES = [16, 64, 256]
# CT_FRACTIONS = ct as fraction of fd (= samples/cell/frame at SPP=1).
# Span aggressive (0.125 = mature in 1/8 frame) to conservative (1.0 = mature
# at end of frame). Goal: find good spots regardless of regime. Bernoulli
# false-trust at: ct=2 → 50%, ct=4 → 12%, ct=8 → 0.8%, ct=16 → 0.0015%.
# HC/preinit/accelDecay compensation deferred to step 15.
CT_FRACTIONS = [0.125, 0.25, 0.5, 1.0]

DEFAULT_SCENES = ["CornellBox_1PointLight", "CornellBox_32PointLights",
                  "BistroInterior", "Sponza"]

BASE_14 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS_14 = []
for (base_name, base_overrides) in BASE_14:
    for fd in FD_VALUES:
        cell_n = int(round(fd**0.5))
        for frac in CT_FRACTIONS:
            ct = max(2, int(round(fd * frac)))
            ct_tag = f"ct{ct:04d}"
            tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_vt010_pm002"
            VARIANTS_14.append((f"{base_name}__{tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(64, ct * 4),
                "varThreshold":                  VT,
                "stderrThreshold":               0.0,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       fd,
                "enableHierarchicalConsistency": False,
                "hierarchicalMuTolerance":       0.20,
                "accelDecayDisagreeThresh":      0.0,
                "pMin":                          PM,
                "bayerN":                        BAYER_N,
                "enableDecayAutoTune":           False,
            }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
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
        variants=VARIANTS_14,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="13", ref_variant="pos_norm__pos__qa012__bayer2x2_cell4x4_ct016_vt010_pm002",
              ref_label="step-13 cell4x4 winner")
write_picks_meta(STEP, inherited_from="13", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Cell-size sweep at step-13 regime (vt=0.03, pm=0.02). "
                        "cell4x4 needs ct≥16 to clear Bernoulli false-trust, "
                        "but ct=16 doesn't mature in 1 frame at SPP=1 (only "
                        "4 samples/cell/frame). cell8x8/16x16/32x32 mature "
                        "16/64/256× faster. vt=0.03 still rejects penumbra-"
                        "aggregation cells via Bernoulli variance. Step 13 "
                        "findings folded in: vt sweep redundant in [0.01,0.08] "
                        "(all reject penumbra), pm=0.02 dominates pm=0.10. "
                        "Scenes extended to Bistro/Sponza for real-scene "
                        "validation. ct={fd/4, fd/2}: floor + safety margin.")
_HEADLESS_SCRIPT_DONE = True
