"""Regenerate step 00 comparison plates + bar plot from existing CSV/captures.
Run via:  runtime/pythondist/python.exe scripts/_regen_step00_plots.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime"))
from VisCache_LadderCommon import (
    make_baseline_comparison_plate, make_baseline_bar_plot,
)

res = 512
for scene in ["Sponza.pyscene", "BistroExterior.pyscene", "BistroInterior.pyscene",
              "CornellBox_32PointLights.pyscene"]:
    try:
        make_baseline_comparison_plate("00", scene, resX=res, resY=res, spp=1,
                                        variants=("vanilla", "rtxdi", "regir", "wsrestir"))
        make_baseline_comparison_plate("00", scene, resX=res, resY=res, spp=4,
                                        variants=("vanilla", "regir", "wsrestir"))
        print(f"[plates] {scene}: ok")
    except Exception as e:
        print(f"[plates] {scene}: SKIP — {e}")

make_baseline_bar_plot("00")
print("[bar] step 00 bar plot regenerated")
