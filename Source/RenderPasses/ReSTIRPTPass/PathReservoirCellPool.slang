/***************************************************************************
 * PathReservoirCellPool.slang
 *
 * World-cell-keyed PathReservoir storage for restirpt_3d (Task #14/#15).
 *
 * Mirrors the design of `Source/RenderPasses/VisCache/WSCellPool.slang`
 * (DI side) but stores PathReservoir per cell instead of DI-proposal slots.
 *
 * Why this exists:
 *
 * Hash-keyed flat reservoir buffer (initial 3D-mode attempt) cannot safely
 * handle concurrent writes from multiple pixels mapping to the same hash
 * slot — non-atomic struct writes interleave, producing torn data
 * (corrupt rcVertex.hit). Downstream gScene.getVertexData(invalid_hit)
 * triggers DXGI_DEVICE_REMOVED.
 *
 * Fix: each cell holds ONE PathReservoir + a fingerprint. First-writer-
 * wins on slot claim via atomic CAS on fingerprint. Reads validate
 * fingerprint match before consuming the reservoir; on mismatch the
 * pixel falls back to its own 2D-keyed reservoir.
 *
 * Layout (per-cell, ~270 B):
 *   uint  fingerprint;  // 0 = empty sentinel; non-zero = claimed
 *   uint  pad[3];       // 16-byte align before PathReservoir
 *   PathReservoir reservoir;  // ~256 B
 *
 * Capacity: same as the pixel-keyed reservoir buffer
 * (screenTiles.x * screenTiles.y * tileStride). On a 512×512 frame this is
 * ~67 MB total — manageable. Future iteration can reduce capacity
 * (since 3D mode trades pixel-1:1 for cell sharing) if perf demands.
 *
 * NOT YET WIRED: this header defines the struct + helpers; allocation,
 * binding, and read/write integration happen in later commits.
 **************************************************************************/
#pragma once
import PathReservoir;
// pcgHashEndpoint — pure int hash, shared with VisCache + WSCellPool to align
// restirpt_3d's cell-keyed pool with the same hash family used elsewhere in the
// world-space caching machinery.
import RenderPasses.VisCache.VisCache;

/// Per-cell slot: PathReservoir + fingerprint for collision detection.
///
/// Total size matches PathReservoir + 16 bytes (4 fingerprint + 12 pad).
/// Padding is for alignment; can be tightened later.
struct PathReservoirCellSlot
{
    uint           fingerprint;     ///< 0 = empty; non-zero = claimed by a pixel hash
    uint           _pad0;
    uint           _pad1;
    uint           _pad2;
    PathReservoir  reservoir;
};

/// Initialize an empty slot (zero fingerprint).
PathReservoirCellSlot prCellSlotInit()
{
    PathReservoirCellSlot s;
    s.fingerprint = 0u;
    s._pad0 = 0u;
    s._pad1 = 0u;
    s._pad2 = 0u;
    s.reservoir.init();
    return s;
}

/// True if a slot is unclaimed (or sentinel).
bool prCellSlotIsEmpty(PathReservoirCellSlot s) { return s.fingerprint == 0u; }

/// True if a slot was claimed by `expectedFingerprint`.
bool prCellSlotMatches(PathReservoirCellSlot s, uint expectedFingerprint)
{
    return s.fingerprint == expectedFingerprint && s.fingerprint != 0u;
}

/// Hash a quantized cell coordinate + normal-bin into a fingerprint.
/// Uses an xor-mul construction (independent salts from the slot hash); the
/// fingerprint is what the SLOT stores so subsequent readers can detect
/// hash collisions and skip stale data.
///
/// Note: fingerprint is NOT frame-keyed — cell-pool slots are sticky
/// once claimed (strict first-writer-wins). The host-side `clearUAV` of
/// the pool's fingerprint field at frame start refreshes claims; see
/// ReSTIRPTPass.cpp::execute().
// Salts: unique per role (slot vs fingerprint) and disjoint from VisCache's
// kSaltA/B/Dist (visibility cache) and WSReservoir's kWSFpSalt (DI reservoir
// fingerprint). Keeps the global pcgHash hash space partitioned.
static const uint kPRCellSlotSalt = 0x7E5C2A11u;
static const uint kPRCellFpSalt   = 0xB3F19DC7u;

// Compile-time cascade depth used by all 6 call sites (TracePass writeOutput
// + 5 reuse passes). Single source of truth so flipping cascade on/off is
// a one-line change.
//
// Storage cost is constant (one cell-pool buffer of fixed capacity, shared
// across levels via per-level salted hash → disjoint slot sub-spaces).
// Compute cost scales with maxLevels: each writer does up to N atomic-CAS,
// each reader does up to N fingerprint checks. In practice most writers
// claim level 0 immediately (early-exit), so amortized cost is small.
//
// Deep cascade: with baseCell = sceneRadius * 1e-5, 32 levels of 2× each
// covers cellSizes from sceneRadius*1e-5 (sub-pixel at any reasonable depth)
// up through sceneRadius * 4e4 (way beyond scene). The footprint heuristic
// picks the level whose cellSize matches the screen-pixel footprint at the
// primary hit's depth. Compute cost amortized — most lookups exit on first
// match.
static const uint kPRCellPoolLevels = 32u;

// Local 3D PCG hash for jitter (mirrors VisCache's pcg3d; copied here to
// avoid pulling pcg3d out of USE_VISCACHE-guarded section). Pure.
uint3 prPcg3d(uint3 v)
{
    v = v * 1664525u + 1013904223u;
    v.x += v.y * v.z;  v.y += v.z * v.x;  v.z += v.x * v.y;
    v ^= v >> 16u;
    v.x += v.y * v.z;  v.y += v.z * v.x;  v.z += v.x * v.y;
    return v;
}

/// Footprint-derived entry level: pick the cascade level whose cell projects
/// to ~kFootprintCellsPerPx screen pixels at the primary hit's depth.
///
/// Analytical projection (matches VisCache's vhfLevelForFootprint pattern):
///   worldPxSize_at_d = d * (frameHeight / focalLength) / screenH_pixels
///   target_cell      = K * worldPxSize_at_d
///   level            = ceil(log2(target_cell / baseCell))
///
/// where K = kFootprintCellsPerPx (default 16, matches VisCache's typical
/// gWSCellPoolFootprintPx). baseCell = sceneRadius * 0.01 (level-0 cell).
///
/// d = distance from camera to primary-hit posW.
/// frameHeight / focalLength = vertical sensor extent / lens length, which
/// equals 2·tan(FOV_v/2). gScene.camera.data exposes both.
///
/// On scenes where camera params are zero/unset (degenerate), falls through
/// to level 0 — the cascade walk fills any gap on collision.
/// K = kFootprintCellsPerPx — pixel² footprint area per cell.
/// Per user 2026-05-08: 0.5 to 1 pixel² gives one cell per pixel reliably.
static const float kFootprintCellsPerPx = 0.5f;

/// Level rounding policy.
///   0 = round nearest (default)
///   1 = next coarser (ceil)   — preferred for tile-style pools
///   2 = next finer   (floor)  — preferred for pixel-target cells
static const uint kPRFootprintRound_Nearest = 0u;
static const uint kPRFootprintRound_Coarser = 1u;
static const uint kPRFootprintRound_Finer   = 2u;

uint prFootprintLevel(float3 posW, float3 cameraPosW, float sceneRadius, uint frameDimY, float frameHeight, float focalLength, uint maxLevels, uint roundMode)
{
    if (focalLength <= 0.f || frameHeight <= 0.f || frameDimY == 0u) return 0u;
    float dist = distance(posW, cameraPosW);
    float worldPxSize = dist * (frameHeight / focalLength) / float(frameDimY);
    // sqrt(K): K is area in pixel², cell SIDE is sqrt(K) × pixel-size.
    float target = sqrt(kFootprintCellsPerPx) * worldPxSize;
    float baseCell = prBaseCell(sceneRadius);
    float lvlF = log2(max(target / baseCell, 1.f));
    int lvl;
    if (roundMode == kPRFootprintRound_Coarser)    lvl = int(ceil(lvlF));
    else if (roundMode == kPRFootprintRound_Finer) lvl = int(floor(lvlF));
    else                                            lvl = int(round(lvlF));
    return uint(clamp(lvl, 0, int(maxLevels) - 1));
}

// Back-compat: round to next-finer (pixel-target default for restirpt).
uint prFootprintLevel(float3 posW, float3 cameraPosW, float sceneRadius, uint frameDimY, float frameHeight, float focalLength, uint maxLevels)
{
    return prFootprintLevel(posW, cameraPosW, sceneRadius, frameDimY, frameHeight, focalLength, maxLevels, kPRFootprintRound_Finer);
}

// Back-compat: distance-based proxy for callers that don't have camera FOV.
uint prFootprintLevel(float3 posW, float3 cameraPosW, float sceneRadius, uint maxLevels)
{
    float dist = distance(posW, cameraPosW);
    float baseScale = max(sceneRadius, 1e-3f);
    float lvlF = log2(max(dist / baseScale, 1.f));
    return uint(clamp(lvlF, 0.f, float(int(maxLevels) - 1)));
}

/// Fingerprint hash. The `level` parameter participates so different
/// cascade levels at the same (q, nb) get distinct fingerprints — key for
/// future multilevel cascade reads (try level L, descend on miss).
uint prCellFingerprint(int3 q, uint nb, uint level)
{
    // Mix nb and level into one uint for the lvl slot of pcgHashEndpoint.
    // Reserve 4 bits for level (0..15) and the rest for nb (only 6 values
    // used). This packs both into pcgHashEndpoint's existing API without
    // adding a 4th hash input.
    uint mixed = (level << 8u) | (nb & 0xFFu);
    uint h = pcgHashEndpoint(q, mixed, kPRCellFpSalt);
    return (h == 0u) ? 1u : h;  // 0 reserved as empty sentinel
}

/// Slot hash. Independent salt from prCellFingerprint so address and
/// fingerprint hashes are uncorrelated (lower false-match rate on
/// collisions). Level participates so different levels map to disjoint
/// slot regions of the same buffer.
uint prCellSlotHash(int3 q, uint nb, uint level)
{
    uint mixed = (level << 8u) | (nb & 0xFFu);
    return pcgHashEndpoint(q, mixed, kPRCellSlotSalt);
}

// Level-0 wrappers preserve the current single-level call sites without
// touching every caller.
uint prCellFingerprint(int3 q, uint nb) { return prCellFingerprint(q, nb, 0u); }
uint prCellSlotHash(int3 q, uint nb)    { return prCellSlotHash(q, nb, 0u); }

/// Base cell size: sceneRadius * 1e-5 (very fine, ~0.001% of scene).
/// Combined with a deep cascade (kPRCellPoolLevels = 32 levels of 2× each,
/// covering 4-billion× range), the analytical footprint level picks a level
/// whose cellSize matches the screen-pixel size at the primary hit's depth.
/// This delivers true pixel-footprint cells at any scene scale (per user
/// 2026-05-08: "adjust the level spread and cell sizes so that any scene
/// supports with 1px cells").
float prBaseCell(float sceneRadius)
{
    return max(sceneRadius * 1e-5f, 1e-7f);
}

/// Cell size for a given level. Level 0 = baseCell; each step doubles.
float prCellSize(float sceneRadius, uint level)
{
    return prBaseCell(sceneRadius) * float(1u << level);     // 2^level scaling
}

/// Compute (q, nb) from world-space primary-hit pos + face normal at a
/// given cascade level. nb is the 6-axis hemicube (shared wsNormalBin).
void prCellQuantize(float3 posW, float3 faceN, float sceneRadius, uint level, out int3 q, out uint nb)
{
    q = int3(floor(posW / prCellSize(sceneRadius, level)));
    nb = wsNormalBin(faceN);
}

// Level-0 wrapper for back-compat.
void prCellQuantize(float3 posW, float3 faceN, float sceneRadius, out int3 q, out uint nb)
{
    prCellQuantize(posW, faceN, sceneRadius, 0u, q, nb);
}

/// Single-call address resolver: posW + faceN → (slot, fingerprint).
/// `capacity` is the cell-pool buffer's slot count (=reservoir buffer size).
/// Both writer and reader must call this with matching args; otherwise they
/// disagree on slot/fingerprint and the pool degenerates.
struct PathReservoirCellAddr
{
    uint slot;
    uint fingerprint;
};
PathReservoirCellAddr prCellResolveAddr(float3 posW, float3 faceN, float sceneRadius, uint capacity, uint level)
{
    int3 q;
    uint nb;
    prCellQuantize(posW, faceN, sceneRadius, level, q, nb);
    PathReservoirCellAddr a;
    a.slot        = prCellSlotHash(q, nb, level) % max(capacity, 1u);
    a.fingerprint = prCellFingerprint(q, nb, level);
    return a;
}

// Level-0 wrapper preserves existing call sites.
PathReservoirCellAddr prCellResolveAddr(float3 posW, float3 faceN, float sceneRadius, uint capacity)
{
    return prCellResolveAddr(posW, faceN, sceneRadius, capacity, 0u);
}

/// Encode a frame-aware fingerprint: upper 8 bits = currentFrame mod 256,
/// lower 24 bits = spatial fingerprint. Both writer and reader compute the
/// same combined value from (q, nb, level, currentFrame); equality at the
/// read site means "this cell was written THIS frame by my pixel".
///
/// HELPER ONLY — not yet wired through cascade write/read. Currently
/// prCellSlotClaim uses the original strict-first-writer-wins CAS on
/// raw spatial fingerprint + per-frame clearUAV. See PORT_NOTES_FRAMEFP.md
/// for the design of switching to the frame-aware variant (drops the
/// clearUAV; requires threading currentFrame through prCellPool*Cascade
/// + 6 call sites in PathTracer.slang).
///
/// Why future-implementer should consider it:
/// - Collapses frame stamp + spatial fp into ONE atomic CAS value,
///   eliminating the two-field race that regressed the earlier separate
///   frameStamp scheme (commit a3129ab reverted because reader saw new
///   stamp + old fp before non-atomic fp write committed).
/// - Drops the per-frame clearUAV at ReSTIRPTPass.cpp:644 → small cost win.
///
/// 8 bits frame = 256-frame cycle (~4 sec at 60 Hz) — acceptable false-
/// match risk during long camera holds. 24 bits fp = 16M unique values;
/// at 256K slots collision rate ~1.5%, at 4K slots ~0.025%.
uint prCellFrameAwareFingerprint(uint spatial_fp, uint currentFrame)
{
    return ((currentFrame & 0xFFu) << 24) | (spatial_fp & 0xFFFFFFu);
}

/// Try to claim a cell-pool slot for `fingerprint`. Atomic CAS on the
/// fingerprint field — strict first-writer-wins, no rewrites.
///
/// Behavior:
/// - Empty slot (fingerprint==0): claim it, return true. ONLY the thread
///   that successfully transitioned the slot from empty wins; subsequent
///   threads with the same fingerprint see prev==fingerprint and return
///   false — important to prevent concurrent non-atomic reservoir writes
///   from tearing the PathReservoir payload (it's ~256 B, no atomic
///   support).
/// - Slot already claimed: return false. Caller must NOT write the
///   reservoir — fall back to pixel-keyed buffer.
///
/// On the read side, prCellSlotRead handles the across-frame stale-data
/// case by validating the fingerprint matches the reader's cell.
bool prCellSlotClaim(RWStructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint fingerprint)
{
    uint prev = 0u;
    InterlockedCompareExchange(pool[slotIdx].fingerprint, 0u, fingerprint, prev);
    return prev == 0u;   // strict first-writer-wins
}

/// Read a cell-pool slot. Returns false (and zeroed reservoir) if the
/// slot is empty OR claimed by a different fingerprint (collision).
/// Takes RWStructuredBuffer because that's what callers have (the buffer
/// is bound as a UAV); reads from RW work fine.
bool prCellSlotRead(RWStructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint expectedFingerprint, out PathReservoir reservoir)
{
    PathReservoirCellSlot s = pool[slotIdx];
    reservoir = s.reservoir;
    return s.fingerprint != 0u && s.fingerprint == expectedFingerprint;
}

// ---------------------------------------------------------------------------
// Cascade helpers: try level 0 first, descend (coarser cells) on miss.
// Read side: returns first level whose slot fingerprint matches.
// Write side: claim at the first level where the slot is empty.
//
// Mirrors VisCache's vhfLookup pattern (try level L, descend on cellGen
// mismatch) but applied to PathReservoir storage. Level-0 writes are the
// most precise; coarser levels capture pixels whose level-0 cell was
// already claimed by another writer, giving a fall-back denser-sampling
// substrate for sparse-cell scenes.
//
// maxLevels=1 preserves single-level (current) behavior: bit-identical to
// the pre-cascade implementation.
// ---------------------------------------------------------------------------

/// Cascading read. Walks levels 0..maxLevels-1; returns the first level whose
/// slot's fingerprint matches the reader's expected fingerprint at that level.
/// Returns false (no level matched) if every level either had an empty slot
/// or a hash collision.
bool prCellPoolReadCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels,
    uint jitterSeed, float jitterPos, uint jitterLevel,
    out PathReservoir reservoir)
{
    for (uint lvl = startLevel; lvl < maxLevels; ++lvl)
    {
        PathReservoirCellAddr a = (jitterPos > 0.f || jitterLevel > 0u)
            ? prCellResolveAddrJittered(posW, faceN, sceneRadius, capacity, lvl, jitterSeed, jitterPos, jitterLevel)
            : prCellResolveAddr(posW, faceN, sceneRadius, capacity, lvl);
        if (prCellSlotRead(pool, a.slot, a.fingerprint, reservoir)) return true;
    }
    reservoir = pool[0].reservoir;   // dummy init for unselected branch (never used by caller)
    return false;
}

// Back-compat: no jitter, startLevel=0.
bool prCellPoolReadCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels, out PathReservoir reservoir)
{
    return prCellPoolReadCascade(pool, posW, faceN, sceneRadius, capacity,
        startLevel, maxLevels, 0u, 0.f, 0u, reservoir);
}

// Back-compat wrapper: startLevel=0.
bool prCellPoolReadCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint maxLevels, out PathReservoir reservoir)
{
    return prCellPoolReadCascade(pool, posW, faceN, sceneRadius, capacity, 0u, maxLevels, reservoir);
}

/// Cascading write. Try-claim at level 0 first; on claim failure (slot
/// already taken), descend to the next coarser level. The reservoir is
/// written at the first successful claim. Returns the level claimed
/// (or maxLevels if all levels had collisions and nothing was written).
uint prCellPoolWriteCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels,
    uint jitterSeed, float jitterPos, uint jitterLevel,
    PathReservoir reservoir)
{
    for (uint lvl = startLevel; lvl < maxLevels; ++lvl)
    {
        PathReservoirCellAddr a = (jitterPos > 0.f || jitterLevel > 0u)
            ? prCellResolveAddrJittered(posW, faceN, sceneRadius, capacity, lvl, jitterSeed, jitterPos, jitterLevel)
            : prCellResolveAddr(posW, faceN, sceneRadius, capacity, lvl);
        if (prCellSlotClaim(pool, a.slot, a.fingerprint))
        {
            pool[a.slot].reservoir = reservoir;
            return lvl;
        }
    }
    return maxLevels;
}

// Back-compat: no jitter, startLevel=0.
uint prCellPoolWriteCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels, PathReservoir reservoir)
{
    return prCellPoolWriteCascade(pool, posW, faceN, sceneRadius, capacity,
        startLevel, maxLevels, 0u, 0.f, 0u, reservoir);
}

// Back-compat wrapper: startLevel=0.
uint prCellPoolWriteCascade(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint maxLevels, PathReservoir reservoir)
{
    return prCellPoolWriteCascade(pool, posW, faceN, sceneRadius, capacity, 0u, maxLevels, reservoir);
}

// ---------------------------------------------------------------------------
// Descending cascade: query coarse → fine. Useful when the reader prefers
// the most-aggregated reservoir (coarser cell = higher M) at the cost of
// some bias from the larger averaging area. Mirror of prCellPoolReadCascade
// but iterates in reverse.
//
// Used by passes that benefit from variance reduction over precision (e.g.
// Spatial/Temporal PathRetrace, where a coarser cell's higher-M reservoir
// drives MIS denominator stability).
// ---------------------------------------------------------------------------
bool prCellPoolReadCascadeDescending(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels,
    uint jitterSeed, float jitterPos, uint jitterLevel,
    out PathReservoir reservoir)
{
    // Walk levels (maxLevels-1, maxLevels-2, ..., startLevel) — coarse → fine.
    for (uint i = 0u; i + startLevel < maxLevels; ++i)
    {
        uint lvl = (maxLevels - 1u) - i;
        PathReservoirCellAddr a = (jitterPos > 0.f || jitterLevel > 0u)
            ? prCellResolveAddrJittered(posW, faceN, sceneRadius, capacity, lvl, jitterSeed, jitterPos, jitterLevel)
            : prCellResolveAddr(posW, faceN, sceneRadius, capacity, lvl);
        if (prCellSlotRead(pool, a.slot, a.fingerprint, reservoir)) return true;
    }
    reservoir = pool[0].reservoir;
    return false;
}

// Back-compat: no jitter, startLevel=0.
bool prCellPoolReadCascadeDescending(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint maxLevels, out PathReservoir reservoir)
{
    return prCellPoolReadCascadeDescending(pool, posW, faceN, sceneRadius, capacity,
        0u, maxLevels, 0u, 0.f, 0u, reservoir);
}

// ---------------------------------------------------------------------------
// Jittered address resolver: stochastic offset of position and level so
// neighbouring pixels hash to slightly-different cells (pos jitter) and/or
// query slightly-different cascade levels (level jitter). Spreads samples
// across neighbour cells, breaks tile boundary artifacts, and lets multiple
// pixels collectively populate more slots.
//
// `jitterSeed` should be deterministic per (pixel, frame) so writers and
// readers at the same logical pixel agree on the jittered cell. Typically
// pcgHashEndpoint(int3(pixel.x, pixel.y, frameIdx), 0u, salt).
//
// `jitterPos` (units of cells, default 0): ±jitterPos/2 per axis additive
// world-space offset before quantize. Set to 1.0 for ±0.5-cell offset
// (matches VisCache's gJitterFilter convention).
//
// `jitterLevel` (max additive level, default 0): MCPG 2025 truncated-
// exponential level offset 0..jitterLevel; most reads stay at base level,
// minority drift up to coarser levels with falling probability ½, ¼, ⅛, …
// ---------------------------------------------------------------------------
PathReservoirCellAddr prCellResolveAddrJittered(
    float3 posW, float3 faceN, float sceneRadius, uint capacity, uint level,
    uint jitterSeed, float jitterPos, uint jitterLevel)
{
    uint lvl = level;
    if (jitterLevel > 0u)
    {
        uint3 r = prPcg3d(uint3(jitterSeed, 0xCAA5u, 0u));
        float u = float(r.x & 0xFFFFu) / 65535.f;
        int dl = clamp(int(-log2(max(1.f - u, 1e-7f))), 0, int(jitterLevel));
        lvl = level + uint(dl);
    }
    float3 jpos = posW;
    if (jitterPos > 0.f)
    {
        uint3 r = prPcg3d(uint3(jitterSeed, 0xBEEF1234u, 0u));
        float3 j = float3(r & 0xFFFFu) / 65535.f - 0.5f;
        jpos += j * jitterPos * prCellSize(sceneRadius, lvl);
    }
    int3 q;
    uint nb;
    prCellQuantize(jpos, faceN, sceneRadius, lvl, q, nb);
    PathReservoirCellAddr a;
    a.slot        = prCellSlotHash(q, nb, lvl) % max(capacity, 1u);
    a.fingerprint = prCellFingerprint(q, nb, lvl);
    return a;
}
