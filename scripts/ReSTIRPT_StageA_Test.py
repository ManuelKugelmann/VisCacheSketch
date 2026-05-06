"""
ReSTIRPT_StageA_Test.py — Phase 3 Stage A unification probe (UNSUPPORTED).

*** UNSUPPORTED 2026-05-06 ***
Stage A is architecturally blocked on Phase 1 §6.2.3 (forced NEE light
reconnection). Bare config flip produces 4× canonical mean_err regression
on Cornell. Three iterations of structurally-correct fixes plateaued at
the same 4× gap. Root cause: Shift.slang's MIS weight degenerates to 1.0
when evaluating BSDF-sample alternative pdf at the light surface (returns
0 for emissive material). Needs Lin 2026 supplemental §5 + Lin 2022
supplemental MIS re-derivation. See:
    Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md §12 #3 + Stage A
    .plans/restirpt-stage-a-unification.md
    .plans/restirpt-forced-nee-reconnection.md (paper re-read priorities)

This script remains for re-engagement after Phase 1 ships. Running it now
will produce the documented 4× regression.

Loads ReSTIRPT_Graph with Stage A config: disableDirectIllumination=False,
useRTXDIDirect=False, useDirectLighting=False.

Usage:
    SCENE_FILE=CornellBox_1AreaLight.pyscene NUM_FRAMES=3 \
        Mogwai.exe --headless --script scripts/RunGraphHeadless.py \
        (with GRAPH_SCRIPT=scripts/ReSTIRPT_StageA_Test.py)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRPT_Graph import render_graph_ReSTIRPT

if 'm' in globals():
    print("[ReSTIRPT_StageA_Test] WARNING: Stage A probe is UNSUPPORTED — "
          "4x canonical mean_err regression. See PORT_NOTES.md §12 #3.")
    m.addGraph(render_graph_ReSTIRPT(
        disableDirectIllumination=False,
        useRTXDIDirect=False,
        useDirectLighting=False,
        maxBounces=4,
    ))
