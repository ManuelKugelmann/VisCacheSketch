"""
ReSTIRNEEPass_VisCache_Graph.py — ReSTIR NEE with VisCache visibility &
light-selection caching enabled.

Thin wrapper around ReSTIRNEEPass_Graph.py mirroring the DI wrapper
pattern: flips visibilityCheck + lightSelection on, AND turns on the
3D cell-reservoir reuse layer (useNEECells=True). Use as the variant-
side comparator when measuring VisCache integration deltas against the
vblind baseline.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRNEEPass_Graph import render_graph_ReSTIRNEEPass

m.addGraph(render_graph_ReSTIRNEEPass(
    useNEECells=True,
    visibilityCheck=True,
    lightSelection=True,
))
