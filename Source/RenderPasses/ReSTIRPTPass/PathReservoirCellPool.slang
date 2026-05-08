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

/// Cell size for a given level. Level 0 is the finest (~1% of scene
/// radius); each step coarsens by 2× (geometric ladder). Matches the
/// VisCache cascade convention (vhfPosASize) but uses a self-contained
/// formula so we don't need to bind VisCache's posACoarse/posAFine.
float prCellSize(float sceneRadius, uint level)
{
    const float kBase = max(sceneRadius * 0.01f, 1e-3f);
    return kBase * float(1u << level);     // 2^level scaling
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
