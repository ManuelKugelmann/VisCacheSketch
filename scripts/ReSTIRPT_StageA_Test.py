"""
ReSTIRPT_StageA_Test.py — Phase 3 Stage A unification probe.

Loads ReSTIRPT_Graph with Stage A config: disableDirectIllumination=False,
useRTXDIDirect=False, useDirectLighting=False. The 2026-05-05 attempt at
this config produced 200k+ Inf pixels per scene; this script lets us
re-run the bare config flip with the current §6.3-active code to see
what specifically blows up at the d=2 boundary.

Usage:
    SCENE_FILE=CornellBox_1AreaLight.pyscene NUM_FRAMES=3 \
        Mogwai.exe --headless --script scripts/RunGraphHeadless.py \
        (with GRAPH_SCRIPT=scripts/ReSTIRPT_StageA_Test.py)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRPT_Graph import render_graph_ReSTIRPT

if 'm' in globals():
    m.addGraph(render_graph_ReSTIRPT(
        disableDirectIllumination=False,
        useRTXDIDirect=False,
        useDirectLighting=False,
        maxBounces=4,
    ))
