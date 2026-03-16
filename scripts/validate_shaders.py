"""
validate_shaders.py — Compare source .slang shaders against deployed release shaders.

Compares by content hash (SHA-256), not file dates, because:
  - git checkout/pull sets mtime to "now", not commit time
  - tar extraction preserves archive timestamps (CI build time)
  - These are unrelated to actual content freshness

Usage (standalone):
    python scripts/validate_shaders.py [--release-dir DIR] [--root-dir DIR]
    Exit code 0 = all OK, 1 = stale or missing shaders.

Usage (from Mogwai embedded Python / smoke_test.py):
    from validate_shaders import check_shaders
    stale, missing = check_shaders(root_dir, deploy_dir)
"""

import hashlib
import os
import sys


# ---------------------------------------------------------------------------
# Source → deploy mappings
# ---------------------------------------------------------------------------
# Each entry: (source_subdir_relative_to_root, deploy_prefix_under_shaders/)
SHADER_MAPPINGS = [
    # Falcor built-in shaders: Falcor/Source/Falcor/**/*.slang → shaders/**/*.slang
    (os.path.join("Falcor", "Source", "Falcor"), ""),
    # Custom pass shaders
    (os.path.join("Source", "RenderPasses", "VisCache"),
     os.path.join("RenderPasses", "VisCache")),
    (os.path.join("Source", "RenderPasses", "ReSTIRPTPass"),
     os.path.join("RenderPasses", "ReSTIRPTPass")),
]


def _file_hash(path):
    """SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_shaders(root_dir, deploy_dir):
    """Compare source .slang files against their deployed counterparts.

    Args:
        root_dir:   Project root (contains Falcor/, Source/).
        deploy_dir: Deployed shaders directory (release/shaders/).

    Returns:
        (stale, missing) — lists of relative paths that differ or are absent.
    """
    stale = []
    missing = []

    for src_subdir, deploy_prefix in SHADER_MAPPINGS:
        src_root = os.path.join(root_dir, src_subdir)
        if not os.path.isdir(src_root):
            continue

        for dirpath, _dirs, filenames in os.walk(src_root):
            for fn in filenames:
                if not fn.endswith(".slang"):
                    continue
                src_path = os.path.join(dirpath, fn)
                rel = os.path.relpath(src_path, src_root)

                if deploy_prefix:
                    deployed = os.path.join(deploy_dir, deploy_prefix, rel)
                else:
                    deployed = os.path.join(deploy_dir, rel)

                # Use deploy_prefix/rel as the display name
                display = os.path.join(deploy_prefix, rel) if deploy_prefix else rel

                if not os.path.isfile(deployed):
                    missing.append(display)
                elif _file_hash(src_path) != _file_hash(deployed):
                    stale.append(display)

    return stale, missing


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate deployed shaders against source tree")
    parser.add_argument("--root-dir", default=None,
                        help="Project root (default: auto-detect from script location)")
    parser.add_argument("--release-dir", default=None,
                        help="Release directory (default: <root>/release)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = args.root_dir or os.path.normpath(os.path.join(script_dir, ".."))
    release_dir = args.release_dir or os.path.join(root_dir, "release")
    deploy_dir = os.path.join(release_dir, "shaders")

    if not os.path.isdir(deploy_dir):
        print(f"[shaders] ERROR: No shaders directory at {deploy_dir}")
        print(f"[shaders] Run download_release to get the release with shaders.")
        return 1

    print(f"[shaders] Comparing source shaders against {deploy_dir} ...")
    stale, missing = check_shaders(root_dir, deploy_dir)

    ok = True
    if missing:
        ok = False
        print(f"[shaders] {len(missing)} shader(s) MISSING from release:")
        for f in sorted(missing)[:20]:
            print(f"  MISSING: {f}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")

    if stale:
        ok = False
        print(f"[shaders] {len(stale)} shader(s) STALE (source differs from deployed):")
        for f in sorted(stale)[:20]:
            print(f"  STALE:   {f}")
        if len(stale) > 20:
            print(f"  ... and {len(stale) - 20} more")

    if ok:
        print(f"[shaders] All deployed shaders match source tree.")
        return 0
    else:
        print(f"[shaders] Fix: re-run quickstart to re-deploy shaders from source.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
