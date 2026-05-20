"""
ReSTIRDIPass_VisCache_Graph.py — ReSTIR DI with VisCache visibility &
light-selection caching enabled.

Thin wrapper around ReSTIRDIPass_Graph.py that flips
enableVisCacheVisibilityCheck and enableVisCacheLightSelection on. Use as
the variant-side comparator when measuring VisCache integration deltas
against the vblind baseline.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRDIPass_Graph import render_graph_ReSTIRDIPass

m.addGraph(render_graph_ReSTIRDIPass(visibilityCheck=True, lightSelection=True))
