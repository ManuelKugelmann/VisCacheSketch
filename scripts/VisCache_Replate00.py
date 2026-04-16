"""
VisCache_Replate00.py — Regenerate step 00 baseline plates from existing EXRs.

Reads each captures/ladder/00/<scene>/s_*_vanilla_hdr.exr and
s_*_vanilla_r1c1_accum_render.png, recomputes error + noise PNGs and plates
under the current metric, rewrites them in place, and refreshes the step-00
CSV + overview plots. Skips rendering — pure Python, seconds per scene vs
minutes for a full Ladder00 rerun.

Usage:
    runtime/pythondist/python.exe scripts/VisCache_Replate00.py
"""
import os, sys, glob, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.join(_project_root, "runtime"))

from VisCache_LadderCommon import (
    _baseline_noise_floor, postprocess_baseline_spp, finalize_baseline,
)


STEP = "00"
STEP_DIR = os.path.join("captures", "ladder", STEP)
_SPP_RE = re.compile(r"s_x(\d+)_(\d+x\d+)_vanilla_hdr\.exr$")

for scene_dir in sorted(glob.glob(os.path.join(STEP_DIR, "CornellBox_*"))):
    if not os.path.isdir(scene_dir):
        continue
    scene_name = os.path.basename(scene_dir)

    hdrs = sorted(glob.glob(os.path.join(scene_dir, "s_x*_*_vanilla_hdr.exr")))
    parsed = [(int(m.group(1)), m.group(2), p) for p in hdrs
              for m in [_SPP_RE.search(p)] if m]
    if not parsed:
        print(f"[replate] {scene_name}: no EXRs, skipping")
        continue

    gt_spp, res_tag, gt_hdr = max(parsed, key=lambda t: t[0])
    noise_floor = _baseline_noise_floor(scene_dir, gt_spp, res_tag)

    for spp, _res, _hdr in sorted(parsed, key=lambda t: t[0]):
        postprocess_baseline_spp(STEP, scene_dir, scene_name,
                                  spp, res_tag, gt_hdr, noise_floor)

finalize_baseline(STEP)
print("[replate] done")
