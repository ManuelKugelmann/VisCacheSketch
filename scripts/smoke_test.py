"""
smoke_test.py  —  Headless smoke test for Mogwai + VisCache plugins.

Validates:
1. Mogwai binary starts in headless mode
2. VisCache render passes are loadable (DLL/SO found and registered)
3. Render graph construction succeeds
4. Exits cleanly (no GPU rendering — just pass registration + graph wiring)

Usage:
    Mogwai --headless --script scripts/smoke_test.py

Exit codes:
    0 — all checks passed
    1 — a check failed (pass not found, graph error, etc.)

On CI without GPU: Mogwai may fail at device creation before reaching this
script. That's expected — the build job validates compilation, and this script
validates runtime integration when a GPU is available.
"""

import os
import sys

REQUIRED_PASSES = [
    "VisCachePass",
]

# ReSTIRPTPass needs 16RooksPattern256.txt deployed to a Falcor data
# directory.  Check for the file before attempting createPass() — the
# constructor FALCOR_THROWs on missing data, which can crash ungracefully.
ROOKS_FILE = "16RooksPattern256.txt"
_script_dir = os.path.dirname(os.path.abspath(__file__))
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

# ---------------------------------------------------------------------------
# 0. Pre-flight: check ReSTIRPTPass data file & register search paths
# ---------------------------------------------------------------------------
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
    sys.exit(1)
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

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")

    # Wire ReSTIRPT only if it was loaded successfully
    if "ReSTIRPTPass" not in warned:
        ReSTIRPT = createPass("ReSTIRPTPass", {'maxBounces': 1})
        g.addPass(ReSTIRPT, "ReSTIRPT")
        g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
        g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
        g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    else:
        g.addEdge("VisCache.debugVis", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    print("  OK: graph built and wired")
except Exception as e:
    print(f"  FAIL: graph construction error — {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Done — exit cleanly (no renderFrame, no scene needed)
# ---------------------------------------------------------------------------
print("[smoke] All checks passed.")
sys.exit(0)
