"""
check_ladderlog_stats.py - verify the numbers cited in docs/LADDERLOG.md
Step RPT_ZOO match the current runtime/captures/ladder/RPT_ZOO/stats.csv.

Re-runs of the ZOO can rotate numbers via run-to-run noise (or fix real
bugs); the LADDERLOG entry needs to stay in sync. This script parses
the RPT_ZOO table block and reports any per-cell mismatch above a small
tolerance.

Usage:
  runtime/pythondist/python.exe scripts/check_ladderlog_stats.py [TOL]

  TOL: max allowed |CSV - LADDERLOG| difference (default 0.01).
  Exit code 0 = all rows match within tolerance; 1 = at least one drift.

Caveat: only parses the three "Step RPT_ZOO" tables at SPP=1, 4, 16.
Other LADDERLOG numbers (RTXDI/DI sections) aren't checked.

Pure-Python tool; no shader paths touched.
"""
import os, sys, csv, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LADDERLOG = os.path.join(ROOT, "docs", "LADDERLOG.md")
CSV_RPT = os.path.join(ROOT, "runtime", "captures", "ladder", "RPT_ZOO", "stats.csv")
CSV_GT  = os.path.join(ROOT, "runtime", "captures", "ladder", "00", "stats.csv")
TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.01


def load_csv_rows():
    rows = {}  # (scene, variant, spp) -> mean_err_pct
    for p in (CSV_RPT, CSV_GT):
        if not os.path.exists(p):
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    spp = int(r["spp"])
                    err = float(r["mean_err_pct"]) if r.get("mean_err_pct") else None
                except (KeyError, ValueError):
                    continue
                if err is None:
                    continue
                rows[(r["scene"], r["variant"], spp)] = err
    return rows


def csv_lookup(rows, scene, kind, spp):
    """kind ∈ {vanilla, R2d, R2dR3d, R3d} → corresponding variant tag with bounce fallback."""
    tag_map = {
        "vanilla": ("vanilla_b4", "vanilla", "vanilla_b1"),
        "R2d":     ("restirpt_R2d_b4", "restirpt_R2d_b3"),
        "R2dR3d":  ("restirpt_R2dR3d_b4", "restirpt_R2dR3d_b3"),
        "R3d":     ("restirpt_R3d_b4", "restirpt_R3d_b3"),
    }
    for t in tag_map[kind]:
        v = rows.get((scene, t, spp))
        if v is not None:
            return v
    return None


# Parse a markdown row like:
# | BistroExterior | 30.247 | 16.535 | 16.731 | 17.103 | +0.568 | -43.5% | -44.7% |
ROW_RE = re.compile(
    r"^\|\s*([A-Za-z_0-9]+)\s*\|\s*"
    r"(\d+\.\d+)\s*\|\s*"      # vanilla
    r"(\d+\.\d+)\s*\|\s*"      # R2d
    r"(\d+\.\d+)\s*\|\s*"      # R2dR3d
    r"(\d+\.\d+)\s*\|"         # R3d
)


def parse_ladderlog_table(ladderlog_text, spp_marker, end_markers):
    """Find the SPP=N table after 'spp_marker' anchor, bounded by the next
    occurrence of any of 'end_markers'. Avoids leaking into adjacent tables.
    Returns {scene: {kind: val}}."""
    out = {}
    anchor_idx = ladderlog_text.find(spp_marker)
    if anchor_idx < 0:
        return out
    # Find the closest end-marker after the anchor.
    end_idx = len(ladderlog_text)
    for em in end_markers:
        pos = ladderlog_text.find(em, anchor_idx + len(spp_marker))
        if pos >= 0:
            end_idx = min(end_idx, pos)
    sub = ladderlog_text[anchor_idx : end_idx]
    for line in sub.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        scene = m.group(1)
        van  = float(m.group(2))
        r2d  = float(m.group(3))
        r2d3 = float(m.group(4))
        r3d  = float(m.group(5))
        out[scene] = {"vanilla": van, "R2d": r2d, "R2dR3d": r2d3, "R3d": r3d}
    return out


def main():
    if not os.path.exists(LADDERLOG):
        sys.exit(f"[check] {LADDERLOG} missing")
    with open(LADDERLOG, encoding="utf-8") as f:
        text = f.read()

    csv_rows = load_csv_rows()
    if not csv_rows:
        sys.exit(f"[check] no CSV rows found in {CSV_RPT} / {CSV_GT}")

    spp_anchors = {
        1:  "**SPP=1 (cold-cell regime):**",
        4:  "**SPP=4:**",
        16: "**SPP=16:**",
    }
    # End-of-table markers — any of these terminates the scan window.
    end_markers = ["**SPP=", "**Architectural", "## ", "### "]

    drift = 0
    checked = 0
    for spp, anchor in spp_anchors.items():
        log_rows = parse_ladderlog_table(text, anchor, end_markers)
        if not log_rows:
            print(f"[check] SPP={spp}: no LADDERLOG table parsed (anchor '{anchor}' not found or no rows)")
            continue
        for scene, kinds in log_rows.items():
            for kind, log_val in kinds.items():
                csv_val = csv_lookup(csv_rows, scene, kind, spp)
                if csv_val is None:
                    print(f"[check] SPP={spp} {scene} {kind}: LADDERLOG says {log_val:.3f} but CSV has no row")
                    drift += 1
                    continue
                if abs(csv_val - log_val) > TOL:
                    print(f"[check] DRIFT SPP={spp} {scene} {kind}: LADDERLOG {log_val:.3f}  CSV {csv_val:.3f}  delta={csv_val - log_val:+.3f}")
                    drift += 1
                checked += 1

    if drift == 0:
        print(f"[check] OK — {checked} LADDERLOG cells all match CSV within ±{TOL}")
        sys.exit(0)
    else:
        print(f"[check] {drift} cell(s) drifted beyond ±{TOL} tolerance (checked {checked} total)")
        print(f"[check] regenerate the LADDERLOG table via:")
        print(f"          runtime/pythondist/python.exe scripts/audit_rpt_zoo_R3d_vs_R2d.py --all --md")
        sys.exit(1)


if __name__ == "__main__":
    main()
