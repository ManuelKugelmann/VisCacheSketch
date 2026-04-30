"""
VisCache_Ladder18.py - vt + stderr sweep on Sponza.

Hypothesis: Sponza's 33% ceiling is from vt=0.01 categorically rejecting
penumbra cells. Loosening vt or activating stderr-gate (which trusts
based on N regardless of mu) should unlock more savings — at the cost
of accepting some bias-by-aggregation.

Sweep at step-14 winner config (cell4x4 ct=2):
  vt     ∈ {0.05, 0.10, 0.20}
  stderr ∈ {0.0 (off), 0.05}
= 6 variants. Sponza only. ~5 min.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "18"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

SUBFRAME_N = 2; CT = 2; PM = 0.02

# Compact 4-axis sweep targeting Sponza ceiling break:
#   vt    ∈ {0.05, 0.10}    — relaxed Bernoulli rejection
#   se    ∈ {0.0, 0.05}     — stderr-gate add-on
#   fd    ∈ {16, 256}       — cell4x4 vs cell16x16 entry
#   cwf   ∈ {12, 24}        — narrower vs wider cascade write window
# = 16 variants × 3 SPP = 48 runs ~5-7 min on Sponza only.
VT_VALUES  = [0.05, 0.10]
SE_VALUES  = [0.0, 0.05]
FD_VALUES  = [16, 256]
CWF_VALUES = [12, 24]

DEFAULT_SCENES = ["Sponza"]

BASE_18 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS_18 = []
for (base_name, base_overrides) in BASE_18:
    for vt in VT_VALUES:
        for se in SE_VALUES:
            for fd in FD_VALUES:
                for cwf in CWF_VALUES:
                    cell_n = int(round(fd**0.5))
                    vt_tag = f"vt{int(round(vt*1000)):03d}"
                    se_tag = f"se{int(round(se*1000)):03d}"
                    cwf_tag = f"cwf{cwf:02d}"
                    tag = (f"bayer{SUBFRAME_N}x{SUBFRAME_N}_cell{cell_n}x{cell_n}_"
                           f"ct{CT:03d}_{vt_tag}_{se_tag}_{cwf_tag}_pm002")
                    VARIANTS_18.append((f"{base_name}__{tag}", {
                        **base_overrides,
                        "bootThreshold":                 CT,
                        "matureThreshold":               max(64, CT * 4),
                        "varThreshold":                  vt,
                        "stderrThreshold":               se,
                        "bootThresholdFactorFootprintPx": 0.0,
                        "forceDescendFootprintPx":       fd,
                        "cascadeWindowForward":          cwf,
                        "enableHierarchicalConsistency": False,
                        "hierarchicalMuTolerance":       0.20,
                        "accelDecayDisagreeThresh":      0.0,
                        "pMin":                          PM,
                        "subframeN":                     SUBFRAME_N,
                        "enableDecayAutoTune":           False,
                    }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, "tableCapacity": 1 << 25}
MF_CONFIGS = [(0, 0, 1, 1), (0, 0, 4, 1), (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    run_baseline(step_name="00", frame_configs=[(0, 0, 1)],
                  scene_file=scene_file, resX=res, resY=res,
                  extra_spp=[4, 16], mogwai_globals=globals())
    run_variants(step_name=STEP, frame_configs=MF_CONFIGS,
                  scene_file=scene_file, variants=VARIANTS_18,
                  resX=res, resY=res, mogwai_globals=globals(),
                  step_overrides=STEP_OVERRIDES)

finalize_step(STEP, inherited_winners=[], ref_step=None)
write_picks_meta(STEP, inherited_from="14", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="vt + stderr sweep on Sponza. Tests whether trust-gate "
                        "loosening unlocks more rays_saved past the 33% ceiling.")
_HEADLESS_SCRIPT_DONE = True
