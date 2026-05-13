/***************************************************************************
 * PathReservoirCellPool.slang
 *
 * World-cell-keyed PathReservoir storage for restirpt_3d (Task #14/#15).
 *
 * Mirrors the design of `Source/RenderPasses/VisCache/CellPool.slang`
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
import RenderPasses.CacheCommon.CacheHash;  // pcg3d, pcgHashEndpoint (Phase C-light migration)
import PathReservoir;
// pcgHashEndpoint — pure int hash, shared with VisCache + CellPool to align
// restirpt_3d's cell-keyed pool with the same hash family used elsewhere in the
// world-space caching machinery.
import RenderPasses.VisCache.VisCache;

/// Per-cell slot: PathReservoir + three single-purpose header words.
///
/// Frame-CAS scheme keeps three concerns in three separate fields:
///   fingerprint - 32-bit spatial hash (cell coords + faceN + level).
///                 Full entropy. ONLY for collision detection between
///                 different cells that hash to the same slot index.
///                 Never contains frame info.
///   frameStamp  - currentFrame value of the latest writer to CLAIM this
///                 slot (via InterlockedMax). The "only 1 writer per
///                 frame" gate. Strictly monotonic.
///   ready       - currentFrame value of the latest writer to COMPLETE
///                 its payload write. Set as the final atomic step in
///                 the write protocol. Reader gates on ready==currentFrame
///                 to avoid torn-payload reads.
///
/// Total: PathReservoir + 16 bytes (4 fingerprint + 4 frameStamp + 4 ready + 4 pad).
struct PathReservoirCellSlot
{
    uint           fingerprint;     ///< spatial hash (0 = empty sentinel)
    uint           frameStamp;      ///< frame-CAS lock: latest claimer's currentFrame
    uint           ready;           ///< publication flag: latest committer's currentFrame
    uint           _pad;
    PathReservoir  reservoir;
};

/// Initialize an empty slot (all header words zero).
PathReservoirCellSlot prCellSlotInit()
{
    PathReservoirCellSlot s;
    s.fingerprint = 0u;
    s.frameStamp = 0u;
    s.ready = 0u;
    s._pad = 0u;
    s.reservoir.init();
    return s;
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
// kSaltA/B/Dist (visibility cache) and Reservoir's kWSFpSalt (DI reservoir
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

// (Local prPcg3d removed — pcg3d now lives in CacheCommon.CacheHash, imported above.)

/// Footprint-derived entry level: pick the cascade level whose cell projects
/// to ~kFootprintCellsPerPx screen pixels at the primary hit's depth.
///
/// Analytical projection (matches VisCache's vhfLevelForFootprint pattern):
///   worldPxSize_at_d = d * (frameHeight / focalLength) / screenH_pixels
///   target_cell      = K * worldPxSize_at_d
///   level            = ceil(log2(target_cell / baseCell))
///
/// where K = kFootprintCellsPerPx (default 16, matches VisCache's typical
/// gCellPoolFootprintPx). baseCell = sceneRadius * 0.01 (level-0 cell).
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
/// given cascade level. nb is the 6-axis hemicube (shared normalBin).
void prCellQuantize(float3 posW, float3 faceN, float sceneRadius, uint level, out int3 q, out uint nb)
{
    q = int3(floor(posW / prCellSize(sceneRadius, level)));
    nb = normalBin(faceN);
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

/// Frame-CAS claim: atomic InterlockedMax on the separate frameStamp field
/// elects exactly one winner per (slot, frame). The spatial fingerprint is
/// stored separately (no bit-mixing) and used by the reader to detect
/// cross-cell collisions inside the slot.
///
/// Returns true if THIS thread is the first-writer for this slot at
/// `currentFrame` and should:
///   1. Non-atomically write `pool[slot].fingerprint = spatialFp`.
///   2. Non-atomically write `pool[slot].reservoir = payload`.
///   3. Call prCellSlotFinalizeFrameCAS to atomically publish `ready = currentFrame`.
///
/// Why InterlockedMax instead of CompareExchange:
/// - Max is monotonic: an older-frame stamp can never displace a newer one.
/// - First-writer-per-frame is naturally elected by "I'm the thread that
///   observed prev < currentFrame"; subsequent waves observe prev == currentFrame
///   and short-circuit. No need to know the previous frame's exact value to CAS against.
/// - The single Max atomic absorbs both the empty-slot and stale-slot cases.
///   No 2nd-CAS-overwrite path → no torn-payload race.
bool prCellSlotClaimFrameCAS(RWStructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint currentFrame)
{
    uint prev = 0u;
    InterlockedMax(pool[slotIdx].frameStamp, currentFrame, prev);
    return prev < currentFrame;   // I'm the first-writer-this-frame iff stamp advanced under me
}

/// Finalize a frame-CAS claim after the payload write completes.
/// Atomically publishes `ready = currentFrame` so readers can consume.
/// MUST be called by any caller that received true from prCellSlotClaimFrameCAS.
///
/// The reader checks ready == currentFrame AND frameStamp == currentFrame
/// AND fingerprint == expected; ready lags frameStamp during the writer's
/// non-atomic payload write so readers naturally reject mid-write state.
void prCellSlotFinalizeFrameCAS(RWStructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint currentFrame)
{
    uint prev = 0u;
    InterlockedExchange(pool[slotIdx].ready, currentFrame, prev);
}

// ---------------------------------------------------------------------------
// Cascade helpers: try level 0 first, descend (coarser cells) on miss.
//
// Mirrors VisCache's vhfLookup pattern (try level L, descend on cellGen
// mismatch) but applied to PathReservoir storage. Level-0 writes are the
// most precise; coarser levels capture pixels whose level-0 cell was
// already claimed by another writer, giving a fall-back denser-sampling
// substrate for sparse-cell scenes.
// ---------------------------------------------------------------------------

/// Cascading write.
///
/// Per cascade level:
///   1. Resolve (slot, spatialFp) for this (posW, faceN, level).
///   2. InterlockedMax-claim frameStamp = currentFrame. If I'm the winner
///      (prev < currentFrame), I OWN this slot for this frame.
///   3. Non-atomically write spatialFp + payload.
///   4. Atomically publish ready = currentFrame.
///
/// Loser threads at level L just fall through to the next coarser level.
/// One winner per frame per slot → no torn-payload race.
uint prCellPoolWriteCascadeFrameCAS(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels,
    uint jitterSeed, float jitterPos, uint jitterLevel,
    uint currentFrame,
    PathReservoir reservoir)
{
    for (uint lvl = startLevel; lvl < maxLevels; ++lvl)
    {
        PathReservoirCellAddr a = (jitterPos > 0.f || jitterLevel > 0u)
            ? prCellResolveAddrJittered(posW, faceN, sceneRadius, capacity, lvl, jitterSeed, jitterPos, jitterLevel)
            : prCellResolveAddr(posW, faceN, sceneRadius, capacity, lvl);
        if (prCellSlotClaimFrameCAS(pool, a.slot, currentFrame))
        {
            // Won the frame for this slot. Write fingerprint + payload non-
            // atomically — no other writer touches this slot this frame.
            pool[a.slot].fingerprint = a.fingerprint;
            pool[a.slot].reservoir   = reservoir;
            // Publish: readers gate on ready==currentFrame AND frameStamp==currentFrame.
            prCellSlotFinalizeFrameCAS(pool, a.slot, currentFrame);
            return lvl;
        }
    }
    return maxLevels;
}

/// Frame-CAS variant of cascading read. Returns the first level whose slot
/// is in the published-this-frame state matching the reader's spatial fp.
///
/// Three-field gate, all must hold:
///   ready       == currentFrame  (writer's payload write is complete)
///   frameStamp  == currentFrame  (slot was claimed by some writer this frame)
///   fingerprint == expectedSpatial  (writer is at the SAME cell, not a hash collision)
///
/// Stale-frame slots (older frameStamp) fail (1) and (2). Mid-write slots
/// (frameStamp updated but ready still old) fail (1). Cross-cell collisions
/// pass (1) + (2) but fail (3). No torn-payload reads.
bool prCellPoolReadCascadeFrameCAS(
    RWStructuredBuffer<PathReservoirCellSlot> pool,
    float3 posW, float3 faceN, float sceneRadius, uint capacity,
    uint startLevel, uint maxLevels,
    uint jitterSeed, float jitterPos, uint jitterLevel,
    uint currentFrame,
    out PathReservoir reservoir)
{
    for (uint lvl = startLevel; lvl < maxLevels; ++lvl)
    {
        PathReservoirCellAddr a = (jitterPos > 0.f || jitterLevel > 0u)
            ? prCellResolveAddrJittered(posW, faceN, sceneRadius, capacity, lvl, jitterSeed, jitterPos, jitterLevel)
            : prCellResolveAddr(posW, faceN, sceneRadius, capacity, lvl);
        PathReservoirCellSlot s = pool[a.slot];
        if (s.ready == currentFrame && s.frameStamp == currentFrame && s.fingerprint == a.fingerprint)
        {
            reservoir = s.reservoir;
            return true;
        }
    }
    reservoir = pool[0].reservoir;   // dummy init
    return false;
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
        uint3 r = pcg3d(uint3(jitterSeed, 0xCAA5u, 0u));
        float u = float(r.x & 0xFFFFu) / 65535.f;
        int dl = clamp(int(-log2(max(1.f - u, 1e-7f))), 0, int(jitterLevel));
        lvl = level + uint(dl);
    }
    float3 jpos = posW;
    if (jitterPos > 0.f)
    {
        uint3 r = pcg3d(uint3(jitterSeed, 0xBEEF1234u, 0u));
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
