"""
VisCache_Replot.py — Regenerate overview plots from existing ladder CSV data.

Does not re-render anything; reads captures/ladder/{step}/stats.csv directly.

Usage:
    runtime/pythondist/python.exe scripts/VisCache_Replot.py [step ...]
    # e.g. python VisCache_Replot.py 01 02
    # default: all steps with a stats.csv
"""
import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress falcor import error — plot_overviews only needs csv + matplotlib
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PROJECT_ROOT", _project_root)
# plot_overviews uses relative paths — must run from runtime/
os.chdir(os.path.join(_project_root, "runtime"))

from VisCache_LadderCommon import plot_overviews, _step_csv

steps = sys.argv[1:] if len(sys.argv) > 1 else None

if steps is None:
    # Auto-discover steps that have a stats.csv
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "runtime", "captures", "ladder", "*", "stats.csv")
    found = sorted(glob.glob(pattern))
    steps = [os.path.basename(os.path.dirname(p)) for p in found]

if not steps:
    print("[replot] No stats.csv files found under runtime/captures/ladder/")
    sys.exit(0)

for step in steps:
    print(f"[replot] Step {step} ...")
    outs = plot_overviews(step)
    if outs:
        for out in outs:
            if out:
                print(f"[replot]   -> {out}")
    else:
        print(f"[replot]   (no data)")
