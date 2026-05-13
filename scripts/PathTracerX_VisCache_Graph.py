"""
PathTracerX_VisCache_Graph.py  —  PathTracerX (forked PathTracer) + VisCache.

Tests the forked plugin against the same graph builder as PathTracer_Graph
so we can compare PathTracerX vs upstream PathTracer for parity.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

m.addGraph(render_graph_PathTracer(viscache=True, passClassName="PathTracerX"))
