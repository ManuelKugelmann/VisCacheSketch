"""compute_worse_metrics.py - Compute worse_* metrics from existing step 14 EXRs.

Walks step 14 capture dirs, loads cache (accumulator) + vanilla + GT EXRs,
runs compute_render_error_signed_hdr on each, prints worse_* metrics
ranked by worse_artifact_5_pct ascending. No re-render needed.
"""
import os, sys, re, io, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from viscache_exr import compute_render_error_signed_hdr

STEP_DIR = "runtime/captures/ladder/14"
BASELINE_DIR = "runtime/captures/ladder/00"
GT_SPP = 4096

scenes = ["CornellBox_1PointLight", "CornellBox_32PointLights", "BistroInterior", "Sponza"]

rows = []
for scene in scenes:
    scene_capture = os.path.join(STEP_DIR, scene, "raw")
    baseline_dir  = os.path.join(BASELINE_DIR, scene)
    gt_path = os.path.join(baseline_dir, f"s_x{GT_SPP}_512x512_vanilla_hdr.exr")
    if not os.path.exists(gt_path):
        print(f"  [skip] {scene}: GT missing")
        continue
    if not os.path.isdir(scene_capture):
        continue
    for fn in sorted(os.listdir(scene_capture)):
        m = re.match(r"(.+)\.AccumulatePass\.output\.(\d+)\.exr$", fn)
        if not m: continue
        variant_name, spp = m.group(1), int(m.group(2))
        cache_path = os.path.join(scene_capture, fn)
        van_path = os.path.join(baseline_dir, f"s_x{spp}_512x512_vanilla_hdr.exr")
        if not os.path.exists(van_path):
            continue
        # Run the same metric computation; outpath unused (overwrites a tmp).
        tmp_out = "/tmp/_unused_metric.png"
        try:
            stats = compute_render_error_signed_hdr(cache_path, van_path, gt_path, tmp_out)
        except Exception as e:
            print(f"  [err] {variant_name} x{spp}: {e}")
            continue
        if stats is None:
            continue
        # Extract cell+ct from variant name.
        cm = re.search(r"cell(\d+)x\d+_ct(\d+)", variant_name)
        if not cm: continue
        cell_n = int(cm.group(1)); ct = int(cm.group(2))
        rows.append({
            "scene": scene, "spp": spp, "cell": cell_n, "ct": ct,
            "worse_area": stats.get("worse_area_pct") or 0.0,
            "worse_mean": stats.get("worse_mean_pct") or 0.0,
            "worse_art5": stats.get("worse_artifact_5_pct") or 0.0,
            "art5_d":     stats.get("artifact_5_minus_vanilla_pct") or 0.0,
            "err_d":      stats.get("err_minus_vanilla_pct") or 0.0,
        })

# Print sorted by worse_artifact_5 ascending (best first), per (scene, spp).
from collections import defaultdict
by_group = defaultdict(list)
for r in rows: by_group[(r["scene"], r["spp"])].append(r)
print(f"\n{'Scene':<24} {'SPP':>3}  {'cell':>4} {'ct':>4} {'worse_area':>10} {'worse_mean':>10} {'worse_art5':>10} {'art5Δ':>7} {'errΔ':>7}")
for (scene, spp), group in sorted(by_group.items()):
    group.sort(key=lambda r: r["worse_art5"])
    print(f"--- {scene} SPP=x{spp} (best top, by worse_art5) ---")
    for r in group[:5]:
        print(f"{scene:<24} x{spp:<2} {r['cell']:>3}x{r['cell']:<2} {r['ct']:>4}"
              f" {r['worse_area']:>9.2f}% {r['worse_mean']:>9.2f}pp {r['worse_art5']:>8.2f}pp"
              f" {r['art5_d']:>+6.2f} {r['err_d']:>+6.2f}")
