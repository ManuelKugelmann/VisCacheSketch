"""
VisCache_Repostprocess.py — Regenerate per-variant PNGs, plate, CSV rows, and
overview plots from archived raw EXRs (captures/ladder/<step>/<scene>/raw/).

Does NOT invoke Mogwai / re-render. Useful when a metric definition changes
(error formula, mask logic, colormap, plate layout) and you want to re-cut
the visualisations without re-rendering — typically minutes vs hours.

Reads captures/ladder/<step>/stats.csv to recover each variant's prefix.
Effective-spp / frames / warmup / subframeN are parsed from the KEY column
(prefix encodes them as `s_<eff_spp>_x<frames>_<wf>o<wr>o<NxN>_<resXxresY>_`)
rather than from the spp/frames CSV columns — this is robust against the
old append_stats_csv quirk where the spp column stored *effective* spp,
and a previous bug double-multiplied frames at the next reprocess.

Usage:
    runtime/pythondist/python.exe scripts/VisCache_Repostprocess.py [step ...]
    # e.g. python VisCache_Repostprocess.py 01 05
    # default: all steps with a stats.csv
"""
import os, sys, csv, glob, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Match the prefix encoding produced by run_variants:
#   s_<eff_spp>_x<frames>_<warmupFirst>o<warmupRun>o<NxN>_<resXxresY>_
_KEY_RE = re.compile(r'_s_(\d+)_x(\d+)_(\d+)o(\d+)o(\d+)x\d+_')

# Skip Falcor — only postprocess / plotting side of the common module is needed.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PROJECT_ROOT", _project_root)
os.chdir(os.path.join(_project_root, "runtime"))

from VisCache_LadderCommon import (
    postprocess_variant, plot_overviews, copy_summary_to_root, _step_csv,
)


def _int_or(row, key, default):
    try:
        return int(row.get(key) or default)
    except (ValueError, TypeError):
        return default


def _repostprocess_step(step):
    step_dir = os.path.join("captures", "ladder", step)
    csv_path = _step_csv(step)
    if not os.path.exists(csv_path):
        print(f"[repost] step {step}: no stats.csv, skipping")
        return

    with open(csv_path, newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if all(k in r for k in ("scene", "variant", "key", "frames"))]

    count = 0
    for row in rows:
        scene        = row["scene"]
        variant_name = row["variant"]
        key          = row["key"]
        # Key format: f"{scene}_{prefix.rstrip('_')}" — recover prefix.
        if not key.startswith(scene + "_"):
            continue
        prefix = key[len(scene) + 1:] + "_"

        # Parse capture parameters from the KEY (prefix encodes them).
        # Falling back to CSV cols would inherit the old append_stats_csv
        # quirk where spp meant *effective* and risk double-multiplying.
        m_key = _KEY_RE.search(key)
        if m_key:
            eff_spp      = int(m_key.group(1))
            frames       = int(m_key.group(2))
            warmup_first = int(m_key.group(3))
            warmup_run   = int(m_key.group(4))
            subframe_n   = int(m_key.group(5))
        else:
            frames       = _int_or(row, "frames",       1)
            eff_spp      = _int_or(row, "spp",          1)
            warmup_first = _int_or(row, "warmup_first", 0)
            warmup_run   = _int_or(row, "warmup_run",   0)
            subframe_n   = _int_or(row, "subframe_n",   1)
        # postprocess_variant multiplies its `frames` × `spp` internally to
        # get effective_spp; recover raw_spp accordingly.
        raw_spp = max(1, eff_spp // max(1, frames))

        capture_dir = os.path.join(step_dir, scene)

        # Raw EXRs must be present for reprocessing. (Old captures with no
        # raw/ archive can't be reprocessed — skip them silently.)
        raw_dir = os.path.join(capture_dir, "raw")
        if not (os.path.exists(raw_dir)
                and glob.glob(os.path.join(raw_dir, f"{variant_name}.*.exr"))):
            continue

        print(f"[repost] step {step} {scene} {variant_name}")
        postprocess_variant(
            step, scene, capture_dir, prefix, variant_name,
            frames=frames, spp=raw_spp,
            warmup_first=warmup_first, warmup_run=warmup_run, subframe_n=subframe_n,
        )
        count += 1

    print(f"[repost] step {step}: reprocessed {count} variants")
    if count > 0:
        plot_overviews(step)
        copy_summary_to_root(step)


steps = sys.argv[1:] if len(sys.argv) > 1 else None
if steps is None:
    pattern = os.path.join(_project_root, "runtime", "captures", "ladder", "*", "stats.csv")
    steps = [os.path.basename(os.path.dirname(p)) for p in sorted(glob.glob(pattern))]

if not steps:
    print("[repost] no steps with stats.csv found")
    sys.exit(0)

for step in steps:
    _repostprocess_step(step)

print("[repost] done")
