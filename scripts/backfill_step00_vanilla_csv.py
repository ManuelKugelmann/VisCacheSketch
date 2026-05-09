"""
backfill_step00_vanilla_csv.py — fill missing vanilla_b{N}_x{S} rows in
step 00's stats.csv from existing EXRs.

Some scenes (e.g. BistroInterior, BistroExterior) have vanilla_b4_x{1,4}
rows but no x{8,16} despite the EXRs existing on disk. This breaks the
audit's GT lookup at SPP=16. This script computes mean_err_pct via OkLab
on those EXRs vs the matching x4096 GT and upserts the missing rows.

Usage:
  runtime/pythondist/python.exe scripts/backfill_step00_vanilla_csv.py [SCENE...]

  SCENE defaults to all scene subdirectories under captures/ladder/00/.
  Tags considered: vanilla, vanilla_b1, vanilla_b4, vanilla_b8 across
  SPPs 1, 2, 4, 8, 16. Adds only rows that are missing from the CSV.

Idempotent: existing rows are not touched.
"""
import os, sys, csv, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from viscache_exr import (compute_render_error_hdr,
                          compute_research_metrics_hdr)

CAPTURES_00 = os.path.join(ROOT, "runtime", "captures", "ladder", "00")
CSV = os.path.join(CAPTURES_00, "stats.csv")

# Match s_x{spp}_{res}_{tag}_hdr.exr where tag is vanilla[_b{N}].
EXR_RE = re.compile(r"^s_x(\d+)_(\d+x\d+)_(vanilla(?:_b\d+)?)_hdr\.exr$")
GT_TAGS = ("vanilla", "vanilla_b1", "vanilla_b4", "vanilla_b8")
SPPS = (1, 2, 4, 8, 16)


def load_existing_keys():
    """Set of `key` values present in stats.csv (e.g. 'BistroInterior_vanilla_b4_x16')."""
    if not os.path.exists(CSV):
        return set()
    keys = set()
    with open(CSV, newline="") as f:
        for r in csv.DictReader(f):
            k = r.get("key", "")
            if k:
                keys.add(k)
    return keys


def find_gt(scene_dir, tag):
    """Find vanilla x4096 EXR for the given tag (or fallback to plain vanilla)."""
    for try_tag in (tag, "vanilla"):
        for f in os.listdir(scene_dir):
            if f.startswith("s_x4096_") and f.endswith(f"_{try_tag}_hdr.exr"):
                return os.path.join(scene_dir, f), try_tag
    return None, None


def write_csv_row(scene, tag, spp, err_stats, research):
    """Append (or upsert if row exists) into stats.csv. Idempotent."""
    # Lazy import: append_baseline_csv handles the upsert + field set.
    from VisCache_LadderCommon import append_baseline_csv
    append_baseline_csv(
        "00", scene, spp,
        mean_err_pct   = err_stats.get("mean_err_pct"),
        mean_noise_pct = None,
        variant=tag,
        rays_traced_pct=None,
        artifact_3_pct=err_stats.get("artifact_3_pct"),
        artifact_5_pct=err_stats.get("artifact_5_pct"),
        artifact_11_pct=err_stats.get("artifact_11_pct"),
        mse=research.get("mse"),
        rmse=research.get("rmse"),
        psnr_db=research.get("psnr_db"),
        relmse=research.get("relmse"),
        smape=research.get("smape"),
        mape=research.get("mape"),
        ms_ssim=research.get("ms_ssim"),
        flip=research.get("flip"),
        chroma_var=research.get("chroma_var"),
    )


def backfill_scene(scene_dir):
    scene = os.path.basename(scene_dir)
    existing = load_existing_keys()
    added = 0
    for fname in os.listdir(scene_dir):
        m = EXR_RE.match(fname)
        if not m:
            continue
        spp_str, res, tag = m.groups()
        spp = int(spp_str)
        if spp == 4096:
            continue  # GT itself; not a row we need
        if spp not in SPPS or tag not in GT_TAGS:
            continue
        key = f"{scene}_{tag}_x{spp}"
        if key in existing:
            continue
        gt_exr, gt_tag = find_gt(scene_dir, tag)
        if not gt_exr:
            print(f"[backfill] {scene}/{fname}: no GT found, skipping")
            continue
        render_exr = os.path.join(scene_dir, fname)
        err_stats = compute_render_error_hdr(render_exr, gt_exr,
                                              os.path.join(scene_dir,
                                                           f"_backfill_{tag}_x{spp}_err.png"))
        if err_stats is None:
            print(f"[backfill] {scene}/{fname}: error compute failed, skipping")
            continue
        research = compute_research_metrics_hdr(render_exr, gt_exr) or {}
        write_csv_row(scene, tag, spp, err_stats, research)
        added += 1
        print(f"[backfill] {scene}: added {tag}_x{spp} (err={err_stats.get('mean_err_pct'):.3f}%, gt={gt_tag})")
    return added


def main():
    if not os.path.isdir(CAPTURES_00):
        sys.exit(f"[backfill] no step 00 dir at {CAPTURES_00}")
    if len(sys.argv) > 1:
        scenes = sys.argv[1:]
    else:
        scenes = [d for d in os.listdir(CAPTURES_00)
                  if os.path.isdir(os.path.join(CAPTURES_00, d))]
    total = 0
    for s in scenes:
        scene_dir = os.path.join(CAPTURES_00, s)
        if not os.path.isdir(scene_dir):
            print(f"[backfill] {s}: not a directory, skipping")
            continue
        total += backfill_scene(scene_dir)
    print(f"[backfill] total rows added: {total}")


if __name__ == "__main__":
    main()
