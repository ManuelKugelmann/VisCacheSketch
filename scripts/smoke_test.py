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

import sys

REQUIRED_PASSES = [
    "VisCachePass",
]
# ReSTIRPTPass depends on data files (16RooksPattern256.txt) that must be
# deployed to the Falcor data directory.  If the data file is missing the
# constructor throws — treat that as a warning, not a hard failure, because
# the smoke test's purpose is verifying plugin registration, not data layout.
OPTIONAL_PASSES = [
    "ReSTIRPTPass",
]

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

for name in OPTIONAL_PASSES:
    try:
        p = createPass(name)
        print(f"  OK: {name}")
        del p
    except Exception as e:
        print(f"  WARN: {name} — {e}")
        warned.append(name)

if missing:
    print(f"[smoke] FAIL: {len(missing)} required passes not found: {missing}")
    sys.exit(1)
if warned:
    print(f"[smoke] NOTE: {len(warned)} optional passes unavailable (data files missing?): {warned}")

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
