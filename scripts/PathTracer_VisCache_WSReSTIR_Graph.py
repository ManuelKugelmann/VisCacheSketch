"""
PathTracer_VisCache_WSReSTIR_Graph.py — PathTracer + VisCache + §9.4 WS-ReSTIR DI.

Delegates to PathTracer_Graph.render_graph_PathTracer with both viscache and
wsReservoirs toggles on. Reservoirs ride the VisCache posA cascade at
`wsLevelOffset` levels coarser than the finest visibility level.

Usage:
    Mogwai.exe --script scripts/PathTracer_VisCache_WSReSTIR_Graph.py --scene Arcade.pyscene
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

m.addGraph(render_graph_PathTracer(viscache=True, wsReservoirs=True))
