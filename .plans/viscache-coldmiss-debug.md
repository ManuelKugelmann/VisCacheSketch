# VisCache Cold Miss Investigation & Debug Test Plan

## Context

VisCache heatmaps show cold misses almost everywhere except at 2D grid-like boundaries (resembling thread group or quantization cell patterns). This plan covers:
1. Root cause analysis of the cold miss pattern
2. Wiring the synthetic hash table test shader (`VisCacheTest.cs.slang`) into the host
3. Fixes for identified bugs

## Root Causes Identified

### A. Eviction race — entries destroyed immediately after insertion (CRITICAL)

The eviction fix (InterlockedExchange for fingerprint + packed) has a race window:

```
T1: vhfFindSlot → slot X (empty, probe 0)
T1: CAS(fingerprint, 0→fp1) → success, packed still 0
                                          ← T2 arrives, probes slot X at depth ≥ 3
                                          ← T2 reads packed, total=0 < threshold=8 → eviction candidate!
                                          ← T2: CAS fails (origFp=fp1 ≠ fp2), eviction path fires
                                          ← T2: Exchange(fingerprint→fp2), Exchange(packed→0)
T1: InterlockedAdd(packed, delta)         → adds to T2's entry (WRONG fp!)
```

Freshly inserted entries with total < 8 are ALWAYS eviction candidates. In the same dispatch, any other thread probing that slot at depth ≥ 3 can immediately evict it.

**Fix**: After CAS failure triggers eviction, re-read total and only evict if still below threshold:
```slang
if (origFp != 0u && origFp != fp)
{
    // Re-check: only evict if entry still has few enough samples
    uint curTotal = gVHFTable[slot].packed & 0xFFFFu;
    if (curTotal >= kEvictBaseCount) continue;  // Entry grew, don't evict
    uint dummy;
    InterlockedExchange(gVHFTable[slot].fingerprint, fp, dummy);
    InterlockedExchange(gVHFTable[slot].packed, 0u, dummy);
}
```
File: `Source/RenderPasses/VisCache/VisCache.slang` ~line 1016 (and same in `VisCacheInsert.cs.slang` ~line 103)

### B. Hash-based canonicalization has tie-breaking regression (MODERATE)

The uncommitted change replaced lexicographic comparison (total order, no ties) with `vhfCanonicalKey` hash comparison (can have ties at ~2^-32 probability). When `canonicalKey(qa) == canonicalKey(qb)` but qa ≠ qb, V(A,B) and V(B,A) produce different orderings → different hash addresses → doubled table pressure for those pairs.

**Fix**: Add tie-breaking fallback to lexicographic comparison:
```slang
uint ka = vhfCanonicalKey(qa), kb = vhfCanonicalKey(qb);
if (ka > kb || (ka == kb && (qa.x > qb.x || (qa.x == qb.x && (qa.y > qb.y || (qa.y == qb.y && qa.z > qb.z))))))
    { int3 tmp = qa; qa = qb; qb = tmp; }
```
File: `Source/RenderPasses/VisCache/VisCache.slang` ~line 464

### C. First-frame cold miss is expected behavior (NOT A BUG)

`vcWriteDiag` reports the gate result from BEFORE the insert. On frame 0 (cold cache), ALL gates miss → 100% cold miss diagnostic. Entries are written AFTER the gate. Frame 1+ should find entries from previous frames. If cold misses persist past frame 1, the cause is A or B above.

## Debug Test Shader Integration Plan

### Files to modify

| File | Changes |
|------|---------|
| `Source/RenderPasses/VisCache/CMakeLists.txt` | Add `VisCacheTest.cs.slang` to `target_sources()` |
| `Source/RenderPasses/VisCache/VisCache.h` | Add `ref<ComputePass>` members for 3 test entry points, `ref<Texture> mpTestOutput`, `bool mRunTest`, `uint32_t mTestMode` |
| `Source/RenderPasses/VisCache/VisCache.cpp` | Compile test shaders in `compile()`, add `runTestPass()`, add output reflection, expose via dict, add UI checkbox |
| `scripts/VisCache_HashTest.py` | New graph script to run test and capture output |

### Host integration (VisCache.cpp)

Follow `runDecayPass()` pattern (lines 545-578):

1. **compile()**: Create 3 ComputePass instances (one per entry point: `csTestInsert`, `csTestVerify`, `csTestInsertAndVerify`). Each needs `USE_VISCACHE=1` define.

2. **execute()**: When `mRunTest` is true:
   - Clear hash table (`clearUAV`)
   - Bind `gVHFTable`, `VisCacheParams`, `TestCB`, `gTestOutput` to each pass
   - Dispatch `csTestInsert` with `(frameDim.x, frameDim.y, 1)` thread groups of 16x16
   - UAV barrier
   - Dispatch `csTestVerify` with same dimensions
   - Expose `mpTestOutput` via dict for capture

3. **reflect()**: Add `testOutput` as RGBA32Float optional output.

4. **renderUI()**: Add test mode dropdown + "Run Test" button.

### Test modes

| Mode | Dispatch | What it isolates | Pass criteria |
|------|----------|-----------------|---------------|
| 0 (identity) | Insert then Verify (2 dispatches) | Basic addressing round-trip: unique entry per pixel | All green (no red pixels) |
| 1 (shared coarse) | Insert then Verify | Atomic contention: 256 threads → same slot | All green |
| 2 (sequential) | Insert then Verify | Probe chain stress at high load | Green at low load, red only when table overflows |
| 3 (same-dispatch) | InsertAndVerify (1 dispatch) | Within-dispatch write visibility | Green = own write visible; red = **addressing bug** (smoking gun) |

### Graph script (`scripts/VisCache_HashTest.py`)

```python
def render_graph_HashTest():
    g = RenderGraph("HashTest")
    vc = createPass("VisCachePass", {"enableTest": True, "testMode": 0})
    g.addPass(vc, "VisCache")
    g.markOutput("VisCache.testOutput")
    return g
```

Run: `.scripts/mogwai-headless.sh VisCache_HashTest.py` — captures test output PNG, check for any red pixels.

## Verification

1. **Build**: `build.bat --skip-setup`
2. **Sync**: `.scripts/sync_to_runtime.sh`
3. **Run test mode 3** (same-dispatch insert+verify): any red pixel = addressing/fingerprint bug
4. **Run test mode 0** (identity, 2-dispatch): red pixels = entries lost between dispatches (eviction race)
5. **Run Ladder00 variants** with eviction race fix applied: cold miss pattern should disappear after warmup
6. **Visual check**: `captures/` directory for test output PNGs — should be all green/blue, no red
