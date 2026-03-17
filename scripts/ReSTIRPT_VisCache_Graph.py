"""
ReSTIRPT_VisCache_Graph.py  —  ReSTIR PT + VisCache (full pipeline).
Delegates to ReSTIRPT_Graph.render_graph_ReSTIRPT(viscache=True).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRPT_Graph import render_graph_ReSTIRPT

m.addGraph(render_graph_ReSTIRPT(viscache=True))
