"""Compare PdfMipmap/Power/LightBVH renders vs vanilla x4096 ground truth.
Reads EXRs captured by PathTracer_PdfMipmap_Test.py and computes mean
err using viscache_exr.compute_render_error.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_exr import compute_render_error_hdr

CAPTURE_DIR = "runtime/captures/pdfmipmap_test"
GT_PATH = "runtime/captures/ladder/00/CornellBox_3AreaLights/s_x4096_512x512_vanilla_hdr.exr"

if not os.path.isfile(GT_PATH):
    print(f"ERROR: ground truth not found: {GT_PATH}")
    sys.exit(1)

results = {}
for sampler in ["LightBVH", "Power", "PdfMipmap"]:
    exr_path = os.path.join(CAPTURE_DIR, f"x16_{sampler}.AccumulatePass.output.16.exr")
    if not os.path.isfile(exr_path):
        print(f"MISSING: {exr_path}")
        continue
    out_png = os.path.join(CAPTURE_DIR, f"x16_{sampler}_err.png")
    err = compute_render_error_hdr(exr_path, GT_PATH, out_png)
    if err is None:
        print(f"FAIL: compute_render_error_hdr returned None for {sampler}")
        continue
    results[sampler] = err
    print(f"{sampler:12s}: mean err = {err['mean_err_pct']:.3f}%   max blob = {err['max_err_pct']:.3f}%")

# Reference: vanilla_x16 in stats.csv = 1.12% (Cornell_3AL_vanilla_x16)
print("\nReference: vanilla_x16 (LightBVH default) err = 1.12% per stats.csv")
print("\nIf PdfMipmap math is correct, all three should be in the 1.0-1.3% band")
print("(stochastic variation from different RNG sequences across samplers).")
