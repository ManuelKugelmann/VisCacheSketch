"""
ReSTIRNEEPass_VisCache_Graph.py  —  ReSTIR NEE with 3D cell-reservoir reuse
at every NEE call (every vertex along the path).

Wires VisCachePass providing the gReservoirs buffer + VisCacheParams cbuffer
via InternalDictionary, and flips ReSTIRNEEPass.useNEECells=True so the slang
USE_NEE_CELLS=1 wedge fires after K-RIS at each NEE event.

Delegates to ReSTIRNEEPass_Graph.render_graph_ReSTIRNEEPass(useNEECells=True).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRNEEPass_Graph import render_graph_ReSTIRNEEPass

m.addGraph(render_graph_ReSTIRNEEPass(useNEECells=True))
