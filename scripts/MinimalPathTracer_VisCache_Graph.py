"""
MinimalPathTracer_VisCache_Graph.py  —  MinimalPathTracer + VisCache (shadow gating §11.2).
Delegates to MinimalPathTracer_Graph.render_graph_MinimalPathTracer(viscache=True).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from MinimalPathTracer_Graph import render_graph_MinimalPathTracer

m.addGraph(render_graph_MinimalPathTracer(viscache=True))
