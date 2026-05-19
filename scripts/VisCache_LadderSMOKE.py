"""
VisCache_LadderSMOKE.py — smoke tests before committing to stages D-F:

  A. Multibounce + cache         : Sponza, maxBounces ∈ {1, 4}, viscache_canonical
  C. Cache-V revalidation        : Sponza, visibilityCheck=True on WS-ReSTIR canonical
  RTXDI RayTraced reference      : Sponza + BistroInt, BiasCorrection::RayTraced

  (B — μ-NEE — deferred. The PathTracer slang gates μ-folding on
  `visInPHat != 0`, not on `enableVisCacheLightSelection`, so the prior
  test was a no-op. Real μ-NEE evaluation is part of c1+c2+c3 — see
  LADDER_PLAN.md "Stage D layered framework".)

Each smoke renders one variant at x4. GTs come from step 00 directly (path
constructed explicitly — no re-render of the x4096 GT).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SMOKE \
        -c "Sponza,BistroInterior"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, run_baseline_rtxdi,
    run_baseline_restir_2d, run_baseline_restir_3d,
    _baseline_noise_floor, kResX, kResY,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "SMOKE"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

# PathTracer DI canonical cache config (LADDERLOG step 18 carry).
# Per directive 2026-05-06 — "regular visibility test optimization should work
# exactly like in the standard vanilla path tracer: use same analytical cache
# entry level, same thresholds, same quantization, same RR params". So the
# cache parameters used in WS-ReSTIR are pulled from the PT-DI canonical chain
# rather than re-tuned for the reservoir context.
PT_CANONICAL_VC = {
    "bootThreshold":                   128,    # ct128
    "matureThreshold":                 512,    # 4× ct
    "varThreshold":                    0.030,  # vt0030
    "pMin":                            0.10,   # pm010
    "bayerN":                          4,      # bayer4×4 (matches cell footprint)
    "forceDescendFootprintPx":         16,     # cell4×4 (16 px²)
    "numLevels":                       8,
    "autoTuneCells":                   True,
    "enableVisCacheAdaptivePMin":      True,
    "enableVisCacheVarianceGate":      True,
    "enableVisCacheDecay":             True,
}

# Common WS-ReSTIR canonical knobs (mirror _run_baseline_restir's recipe).
WSRESTIR_KW = dict(
    viscache=True, reservoirs=True, maxBounces=0, useJitter=True,
    initialCandidates=32, mCap=5.0,
    spatialNeighbours=0, spatialPixelsK=1, spatialPixelsRadius=30,
    cellPool=True, cellPoolDrawK=16, wsCellPoolPrePass=True,
    visInPHat=0,
    prePassEmissiveSampler="PdfMipmap",
    poolAddrMode=1, poolTileSize=16,                # 2D pool (matches restir_2d)
)
WSRESTIR_VC = {
    "enablePixelReservoir": True,
    "cellReservoirMerge": 0,
    **PT_CANONICAL_VC,                                  # PT-DI canonical cache config layered on top
}


def _gt(scene_name, variant_tag="vanilla"):
    """Resolve GT EXR + cached noise floor by pointing at step 00's captures."""
    src_dir = f"captures/ladder/00/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_{variant_tag}_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, variant_tag)
    return gt_hdr, floor


for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # === RTXDI strict reference (BiasCorrection::RayTraced) ===
    # Compares against the default rtxdi (Basic). The RayTraced variant
    # re-traces V during MIS — unbiased, expensive. Establishes the
    # strict-mode reference that paper §12 cache-V revalidation aims to match.
    if scene_name in ("Sponza", "BistroInterior"):
        run_baseline_rtxdi(
            STEP, [(0, 0, 1)], scene_file, resX=res, resY=res,
            capture_spps=(4,), mogwai_globals=globals(),
            biasCorrection="RayTraced",
        )

    # === restir_2d / restir_3d strict-mode equivalents ===
    # Our 2D-tile and 3D-cell pool variants with retrace-on-reuse ENABLED.
    # `retraceOnReuseMode=1` (FullTrace) ≡ RTXDI BiasCorrection::RayTraced —
    # re-traces V at the temporal/spatial reservoir merge sites in
    # PathTracer.slang. Compares against the same scene's restir_2d_vblind /
    # restir_3d_vblind (Basic-equivalents) and the rtxdi_raytraced reference.
    # `retraceOnReuseMode=2` (CacheCV) is the cheap CV+RRR variant — same
    # unbiasedness via cache CV+RRR, lower ray cost.
    if scene_name in ("Sponza", "BistroInterior"):
        for retrace_mode in (1, 2):
            run_baseline_restir_2d(
                STEP, [(0, 0, 1)], scene_file, resX=res, resY=res,
                capture_spps=(4,), mogwai_globals=globals(),
                retraceOnReuseMode=retrace_mode,
            )
            run_baseline_restir_3d(
                STEP, [(0, 0, 1)], scene_file, resX=res, resY=res,
                capture_spps=(4,), mogwai_globals=globals(),
                retraceOnReuseMode=retrace_mode,
            )

    # === A: multibounce + cache (Sponza only; has vanilla_b{1,4} GT) ===
    # Use PathTracer DI canonical cache config explicitly (ct128/vt030/pm010,
    # bayer4x4 + cell4x4, 8 levels with autoTuneCells). Treats the cache the
    # same way the PT-DI ladder canonical does — same thresholds, quantization,
    # RR params.
    if scene_name == "Sponza":
        for mb in (1, 4):
            gt_hdr, floor = _gt(scene_name, f"vanilla_b{mb}")
            if gt_hdr is None:
                print(f"[SMOKE-A] Sponza vanilla_b{mb} GT missing — skip")
                continue

            def _build(spp, mb=mb):
                return render_graph_PathTracer(
                    viscache=True, maxBounces=mb,
                    samplesPerPixel=spp, useJitter=True,
                    extraVCProps=PT_CANONICAL_VC,           # PT-DI canonical
                )

            _run_baseline_variant(
                STEP, [(0, 0, 1)], scene_file, f"smokeA_viscache_b{mb}",
                _build, "AccumulatePass.output",
                capture_spps=(4,), maxBounces=mb,
                resX=res, resY=res, mogwai_globals=globals(),
                gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
            )

    # === C: cache-V revalidation in DI (Sponza) ===
    # Uses PathTracer DI canonical cache config inside the WS-ReSTIR pipeline.
    # `enableVisCacheVisibilityCheck=true` is implicit via VISCACHE_DEFAULTS
    # but the PT_CANONICAL_VC overrides come through extraVCProps.
    if scene_name == "Sponza":
        gt_hdr, floor = _gt(scene_name, "vanilla")
        if gt_hdr is None:
            print(f"[SMOKE-C] Sponza vanilla GT missing — skip")
        else:
            def _build_c(spp):
                return render_graph_PathTracer(
                    samplesPerPixel=spp,
                    visibilityCheck=True,                   # cache CV+RRR for V on
                    lightSelection=False,
                    extraVCProps=WSRESTIR_VC,               # already includes PT_CANONICAL_VC
                    **WSRESTIR_KW,
                )

            _run_baseline_variant(
                STEP, [(0, 0, 1)], scene_file, "smokeC_wsrestir_cacheV",
                _build_c, "AccumulatePass.output",
                capture_spps=(4,), maxBounces=0,
                resX=res, resY=res, mogwai_globals=globals(),
                force_actual_spp=1,
                gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
            )

_HEADLESS_SCRIPT_DONE = True
