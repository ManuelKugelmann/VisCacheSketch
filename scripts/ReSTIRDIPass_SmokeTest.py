"""
ReSTIRDIPass_SmokeTest.py — exercises the standalone ReSTIRDIPass.

Loaded by Mogwai's RunGraphHeadless harness via:
    .scripts/mogwai-headless.sh 'ReSTIRDIPass_SmokeTest.py' 'CornellBox_3AreaLights.pyscene' 1

Expected outcome: graph loads + ReSTIRDIPass compute shader compiles + 1
frame renders without crash. Output will be primitive single-NEE DI (no
K-RIS yet — body lift in progress).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

m.addGraph(render_graph_PathTracer(
    viscache=True,
    wsReservoirs=True,
    maxBounces=0,
    samplesPerPixel=1,
    useReSTIRDIPass=True,   # the new pass under test
))
