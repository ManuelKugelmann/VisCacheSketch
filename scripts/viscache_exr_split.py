"""viscache_exr_split.py — High-level EXR → viridis PNG batch extraction.

Composable section-based splitting of VisCache diagnostic EXR captures.
Mirrors the ladder grid layout and can be used standalone or as a library.

    from viscache_exr_split import split_diag_exrs
    split_diag_exrs("captures/debug", prefix="pos_pos_", sections=["frame", "accum"])

Standalone:
    python viscache_exr_split.py <capture_dir> [prefix] [sections]

Sections: "frame", "accum", "hash", "basic" (frame+accum), "all"
"""
import os, glob

from viscache_exr import write_channel, load_coldmiss_mask, find_exr


# ---------------------------------------------------------------------------
# Sections — composable channel definitions
# ---------------------------------------------------------------------------
# Each entry: (exr_substring, channel_index, output_name, options_string)
# Options (comma-separated):
#   "coldmiss"  — apply coldmiss overlay (black for cold-miss pixels)
#   "normalize" — normalize by channel max before colormap (for unbounded data)

SECTIONS = {
    "frame": [
        ("FrameMeanVarMatSamplesRaw",      0, "frame_variance",    "coldmiss"),
        ("FrameMeanVarMatSamplesRaw",      1, "frame_maturity",    "coldmiss"),
        ("FrameMeanVarMatSamplesRaw",      2, "frame_mean",        "coldmiss"),
        ("FrameMeanVarMatSamplesRaw",      3, "frame_samplesraw",  "coldmiss,normalize"),
        ("FrameLevelProbesSamplesCold",    0, "frame_level",       "coldmiss"),
        ("FrameLevelProbesSamplesCold",    1, "frame_probesteps",  "coldmiss"),
        ("FrameLevelProbesSamplesCold",    2, "frame_samplecount", "coldmiss"),
        ("FrameLevelProbesSamplesCold",    3, "frame_coldmiss",    None),
    ],
    "accum": [
        ("AccumMeanVarMatCount",           0, "accum_variance",   None),
        ("AccumMeanVarMatCount",           1, "accum_maturity",   None),
        ("AccumMeanVarMatCount",           2, "accum_mean",       None),
        ("AccumMeanVarMatCount",           3, "accum_count",      "normalize"),
        ("AccumRaysNoiseErrorCold",        0, "accum_raystraced", None),
        ("AccumRaysNoiseErrorCold",        1, "accum_noise",      None),
        ("AccumRaysNoiseErrorCold",        2, "accum_error",      None),
        ("AccumRaysNoiseErrorCold",        3, "accum_coldmiss",   None),
    ],
    "hash": [
        ("FrameHashAHashBHashABRays", 0, "hash_posA",           "coldmiss"),
        ("FrameHashAHashBHashABRays", 1, "hash_posB",           "coldmiss"),
        ("FrameHashAHashBHashABRays", 2, "hash_combinedAB",     "coldmiss"),
        ("FrameHashAHashBHashABRays", 3, "hash_raysTraced",     None),
    ],
}

SECTIONS["all"] = SECTIONS["frame"] + SECTIONS["accum"] + SECTIONS["hash"]
SECTIONS["basic"] = SECTIONS["frame"] + SECTIONS["accum"]


# ---------------------------------------------------------------------------
# Batch split
# ---------------------------------------------------------------------------

def split_diag_exrs(capture_dir, prefix="", outdir=None, sections=None):
    """Split diagnostic EXRs into named viridis PNGs.

    Args:
        capture_dir:  directory containing EXR files from Mogwai frame capture
        prefix:       filename prefix for output PNGs (e.g. "pos_pos_")
        outdir:       output directory (default: capture_dir)
        sections:     list of section names (default: ["all"])

    Returns: list of output paths.
    """
    if outdir is None:
        outdir = capture_dir
    os.makedirs(outdir, exist_ok=True)

    exrs = glob.glob(os.path.join(capture_dir, "*.exr"))
    if not exrs:
        return []

    coldmiss = load_coldmiss_mask(exrs)
    if coldmiss is not None:
        pct = coldmiss.mean() * 100
        print(f"[exr] Coldmiss: {pct:.1f}% of pixels")

    if sections is None:
        sections = ["all"]
    entries = []
    for s in sections:
        entries.extend(SECTIONS.get(s, []))

    outputs = []
    for exr_pattern, ch_idx, name, opts in entries:
        exr = find_exr(exrs, exr_pattern)
        if exr is None:
            continue
        opts = opts or ""
        mask = coldmiss if "coldmiss" in opts else None
        norm = "normalize" in opts
        outpath = os.path.join(outdir, f"{prefix}{name}.png")
        result = write_channel(exr, ch_idx, outpath, coldmiss=mask, normalize_max=norm)
        if result:
            print(f"[exr] {os.path.basename(result)}")
            outputs.append(result)

    return outputs


if __name__ == "__main__":
    import sys
    capture_dir = sys.argv[1] if len(sys.argv) > 1 else "runtime/captures/debug"
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""
    section_arg = sys.argv[3] if len(sys.argv) > 3 else "all"
    sections = section_arg.split(",")
    outputs = split_diag_exrs(capture_dir, prefix, sections=sections)
    print(f"\n[exr] {len(outputs)} PNGs written to {capture_dir}/")
