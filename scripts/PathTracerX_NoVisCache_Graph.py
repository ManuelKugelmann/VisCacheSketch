"""
PathTracerX_NoVisCache_Graph.py  —  PathTracerX in "vanilla mode" (no VisCache).

Validation graph: confirms PathTracerX produces a render with viscache=False.
Since PathTracerX's VisCache integration is purely gated by `USE_VISCACHE`
defines (and they default to 0 when VisCache pass isn't in the graph), this
should be functionally equivalent to the vanilla upstream Falcor PathTracer.

Useful for parity testing: compare this graph's EXR against PathTracer_Graph.py
(which uses upstream `PathTracer`) — they should be bit-identical.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

m.addGraph(render_graph_PathTracer(viscache=False, passClassName="PathTracerX"))
