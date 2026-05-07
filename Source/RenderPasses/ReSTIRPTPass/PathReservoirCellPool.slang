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
/// fingerprint field — first writer wins.
///
/// Behavior:
/// - Empty slot (fingerprint==0): claim it, return true.
/// - Already claimed by THIS fingerprint: also return true (rewrite OK).
/// - Claimed by a DIFFERENT fingerprint: return false (collision; caller
///   should fall back to pixel-keyed reservoir to avoid corruption).
///
/// Note: this only synchronizes the fingerprint field. The PathReservoir
/// payload write that follows is non-atomic — concurrent writers with the
/// same fingerprint (i.e. same cell) can still produce torn writes if
/// they race. In practice each frame a cell is hit by at most a few
/// pixels (geometry-correlated) and last-writer-wins is acceptable.
bool prCellSlotClaim(RWStructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint fingerprint)
{
    uint prev = 0u;
    InterlockedCompareExchange(pool[slotIdx].fingerprint, 0u, fingerprint, prev);
    if (prev == 0u || prev == fingerprint) return true;
    return false;
}

/// Read a cell-pool slot. Returns false (and zeroed reservoir) if the
/// slot is empty OR claimed by a different fingerprint (collision).
bool prCellSlotRead(StructuredBuffer<PathReservoirCellSlot> pool, uint slotIdx, uint expectedFingerprint, out PathReservoir reservoir)
{
    PathReservoirCellSlot s = pool[slotIdx];
    reservoir = s.reservoir;
    return s.fingerprint != 0u && s.fingerprint == expectedFingerprint;
}
