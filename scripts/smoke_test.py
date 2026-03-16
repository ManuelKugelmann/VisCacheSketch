"""
smoke_test.py  —  Headless smoke test for Mogwai + VisCache plugins.

Validates:
1. Mogwai binary starts in headless mode
2. VisCache render passes are loadable (DLL/SO found and registered)
3. Render graph construction succeeds
4. Exits cleanly (no GPU rendering — just pass registration + graph wiring)

Usage:
    Mogwai --headless --script scripts/smoke_test.py

Errors:
    Raises RuntimeError if a required pass is missing or graph construction fails.
    Does NOT call sys.exit() — Mogwai's embedded Python treats SystemExit as
    an unhandled exception.

On CI without GPU: Mogwai may fail at device creation before reaching this
script. That's expected — the build job validates compilation, and this script
validates runtime integration when a GPU is available.
"""

import os
import sys

REQUIRED_PASSES = [
    "VisCachePass",
]

_script_dir = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 0a. Pre-flight: validate deployed shaders against source tree
# ---------------------------------------------------------------------------
# Compares content hashes (not file dates) because git checkout/pull sets
# mtime to "now" and tar extraction preserves CI build timestamps — neither
# reflects actual content freshness.

# Find project root (contains Falcor/ directory)
_root_candidates = [
    os.path.join(_script_dir, ".."),                    # scripts/
    os.path.join(_script_dir, "..", "..", ".."),         # release/scripts/VisCache/
]
_project_root = None
for _c in _root_candidates:
    if os.path.isdir(os.path.join(_c, "Falcor")):
        _project_root = os.path.normpath(_c)
        break

# Find deploy dir (release/shaders/)
_deploy_candidates = [
    os.path.join(_script_dir, "..", "..", "shaders"),    # release/scripts/VisCache/
    os.path.join(_script_dir, "..", "release", "shaders"),  # scripts/
]
_deploy_dir = None
for _d in _deploy_candidates:
    if os.path.isdir(_d):
        _deploy_dir = os.path.normpath(_d)
        break

if _deploy_dir is None:
    print("[smoke] ERROR: No shaders directory found in release/")
    print("[smoke] This causes 'undefined identifier' errors (e.g. ExplicitLodTextureSampler).")
    print("[smoke] Fix: re-run download_release to get a fresh release with all shaders.")
    raise RuntimeError("No shaders directory found in release/")

if _project_root is not None:
    # Import or inline the validation logic
    sys.path.insert(0, _script_dir)
    try:
        from validate_shaders import check_shaders
        stale, missing = check_shaders(_project_root, _deploy_dir)
        if missing:
            print(f"[smoke] WARNING: {len(missing)} shader(s) missing from release/shaders/:")
            for f in sorted(missing)[:10]:
                print(f"  MISSING: {f}")
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more")
        if stale:
            print(f"[smoke] WARNING: {len(stale)} shader(s) stale (source differs from deployed):")
            for f in sorted(stale)[:10]:
                print(f"  STALE:   {f}")
            if len(stale) > 10:
                print(f"  ... and {len(stale) - 10} more")
        if missing or stale:
            print(f"[smoke] Stale shaders cause 'undefined identifier' or wrong behavior at runtime.")
            print(f"[smoke] Fix: re-run quickstart to re-deploy shaders from source.")
        else:
            print(f"[smoke] All {len(os.listdir(_deploy_dir))}+ deployed shaders match source tree.")
    except Exception as e:
        print(f"[smoke] WARNING: Shader validation failed: {e}")
        print(f"[smoke] Continuing with smoke test...")
else:
    print("[smoke] WARNING: Could not find project root — skipping shader content validation")
    print(f"[smoke] Deploy dir: {_deploy_dir}")

# ---------------------------------------------------------------------------
# 0b. Pre-flight: check ReSTIRPTPass data file & register search paths
# ---------------------------------------------------------------------------
# ReSTIRPTPass needs 16RooksPattern256.txt deployed to a Falcor data
# directory.  Check for the file before attempting createPass() — the
# constructor FALCOR_THROWs on missing data, which can crash ungracefully.
ROOKS_FILE = "16RooksPattern256.txt"
# The script runs from two locations:
#   source tree:  scripts/smoke_test.py           (dirname = scripts/)
#   release:      release/scripts/VisCache/smoke_test.py  (dirname = release/scripts/VisCache/)
# Build paths that work from both locations.
ROOKS_SEARCH_DIRS = [
    # Source tree (from scripts/)
    os.path.join(_script_dir, "..", "Source", "RenderPasses", "ReSTIRPTPass", "Data"),
    # Source tree (from release/scripts/VisCache/)
    os.path.join(_script_dir, "..", "..", "..", "Source", "RenderPasses", "ReSTIRPTPass", "Data"),
    # Deployed release data (from release/scripts/VisCache/)
    os.path.join(_script_dir, "..", "..", "data", "ReSTIRPTPass"),
    # Deployed release data (from scripts/)
    os.path.join(_script_dir, "..", "release", "data", "ReSTIRPTPass"),
]

rooks_found = False
for d in ROOKS_SEARCH_DIRS:
    candidate = os.path.join(d, ROOKS_FILE)
    if os.path.isfile(candidate):
        rooks_found = True
        # Register the *parent* of the data dir so AssetResolver finds
        # "ReSTIRPTPass/16RooksPattern256.txt" via its sub-path lookup.
        data_parent = os.path.normpath(os.path.join(d, ".."))
        abs_data_parent = os.path.abspath(data_parent)
        try:
            from pathlib import Path
            AssetResolver.default_resolver.add_search_path(Path(abs_data_parent))
            print(f"[smoke] Added AssetResolver search path: {abs_data_parent}")
        except Exception:
            pass  # Binding may not be available in all builds
        print(f"[smoke] Found {ROOKS_FILE} at {os.path.normpath(candidate)}")
        break

if not rooks_found:
    print(f"[smoke] WARNING: {ROOKS_FILE} not found in any search path — skipping ReSTIRPTPass")
    for d in ROOKS_SEARCH_DIRS:
        print(f"  checked: {os.path.normpath(d)}")

# ---------------------------------------------------------------------------
# 1. Check that our render passes are registered
# ---------------------------------------------------------------------------
print("[smoke] Checking render pass registration...")
missing = []
warned = []
for name in REQUIRED_PASSES:
    try:
        p = createPass(name)
        print(f"  OK: {name}")
        del p
    except Exception as e:
        print(f"  MISSING: {name} — {e}")
        missing.append(name)

# Only attempt ReSTIRPTPass if data file is present
if rooks_found:
    try:
        p = createPass("ReSTIRPTPass")
        print(f"  OK: ReSTIRPTPass")
        del p
    except Exception as e:
        print(f"  WARN: ReSTIRPTPass — {e}")
        warned.append("ReSTIRPTPass")
else:
    warned.append("ReSTIRPTPass")

if missing:
    print(f"[smoke] FAIL: {len(missing)} required passes not found: {missing}")
    raise RuntimeError(f"Required passes not found: {missing}")
if warned:
    print(f"[smoke] NOTE: {len(warned)} optional passes unavailable: {warned}")

# ---------------------------------------------------------------------------
# 2. Build a minimal render graph to test wiring
# ---------------------------------------------------------------------------
print("[smoke] Building test render graph...")
try:
    g = RenderGraph("SmokeTest")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    VisCache = createPass("VisCachePass", {
        'enableVisCacheRevalidation': True,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(VisCache, "VisCache")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False})
    g.addPass(ToneMapper, "ToneMapper")

    # VisCache is a dictionary-only pass (no graph inputs/outputs).
    # It exposes the hash table via InternalDictionary for downstream passes.

    # Wire ReSTIRPT only if it was loaded successfully
    if "ReSTIRPTPass" not in warned:
        ReSTIRPT = createPass("ReSTIRPTPass", {'maxSurfaceBounces': 1})
        g.addPass(ReSTIRPT, "ReSTIRPT")
        g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
        g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
        g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    else:
        # Fallback: wire PathTracer directly to ToneMapper
        PT = createPass("PathTracer", {'samplesPerPixel': 1})
        g.addPass(PT, "PT")
        g.addEdge("VBuffer.vbuffer", "PT.vbuffer")
        g.addEdge("PT.color", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    print("  OK: graph built and wired")
except Exception as e:
    print(f"  FAIL: graph construction error — {e}")
    raise

# ---------------------------------------------------------------------------
# 3. Done — exit cleanly (no renderFrame, no scene needed)
# ---------------------------------------------------------------------------
print("[smoke] All checks passed.")
# Note: do NOT call sys.exit() — Mogwai's embedded Python treats SystemExit
# as an exception, which causes a crash.  Use Falcor's own exit() binding
# (registered by SampleApp) which cleanly shuts down the application.
exit()
