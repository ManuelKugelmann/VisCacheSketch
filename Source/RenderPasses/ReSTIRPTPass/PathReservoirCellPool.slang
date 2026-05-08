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
/// Uses the same xor-mul construction as the worldcell-offset hash; the
/// fingerprint is what the SLOT stores so subsequent readers can detect
/// hash collisions and skip stale data.
uint prCellFingerprint(int3 q, uint nb)
{
    return ((uint(q.x) * 2654435761u) ^ (uint(q.y) * 1597334677u) ^ (uint(q.z) * 805459861u) ^ (nb * 374761393u))
           | 1u;  // ensure non-zero: 0 is the empty sentinel
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
