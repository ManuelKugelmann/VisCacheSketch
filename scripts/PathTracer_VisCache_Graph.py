"""
PathTracer_VisCache_Graph.py  —  PathTracer + VisCache (shadow gating §11.2).
Delegates to PathTracer_Graph.render_graph_PathTracer(viscache=True).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

m.addGraph(render_graph_PathTracer(viscache=True))
