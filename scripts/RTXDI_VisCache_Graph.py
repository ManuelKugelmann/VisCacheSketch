"""
RTXDI_VisCache_Graph.py  —  RTXDI + VisCache (light selection §11.1).
Delegates to RTXDI_Graph.render_graph_RTXDI(viscache=True).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from RTXDI_Graph import render_graph_RTXDI

m.addGraph(render_graph_RTXDI(viscache=True))
