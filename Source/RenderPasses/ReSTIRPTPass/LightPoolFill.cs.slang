/***************************************************************************
 * LightPoolFill.cs.slang
 *
 * P-axis pool fill pass — STUB. Step 2 of MVP.
 *
 * Per user direction 2026-05-11: shares the WSCellPool struct from
 * VisCache (see LightPool.slang). For now writes a recognizable sentinel
 * so Step 3 (NEE-site reader-side RIS) can verify slot keying works
 * without yet doing real emissiveSampler.sampleLight at insert.
 *
 * Real implementation TODO:
 *   - mirror WSCellPoolIO.slang::wsCellPoolInsert (RIS-at-insert with
 *     pHat × V / sourcePdf weight)
 *   - per-slot proxy shading point (tile-center for P2d, cell-center for
 *     P3d — P3d needs slot->worldPos table since cell hashes are one-way)
 *   - K_pre candidates per slot, drawn from gPathTracer.emissiveSampler
 *
 * Design + 4-day plan: see PORT_NOTES_P_AXIS.md.
 **************************************************************************/
import Scene.Scene;
import PathTracer;     // pulls EnvMapSampler, EmissiveLightSampler, lightPool field
import LightPool;
import RenderPasses.VisCache.WSCellPool;   // direct: slang imports aren't transitive
import Params;

ParameterBlock<PathTracer> gPathTracer;

[numthreads(64, 1, 1)]
void main(uint3 dtid : SV_DispatchThreadID)
{
    const uint slotIdx = dtid.x;
    const uint poolSize = gPathTracer.params.screenTiles.x * gPathTracer.params.screenTiles.y
                          * (kScreenTileDim.x * kScreenTileDim.y);
    if (slotIdx >= max(poolSize, 1u)) return;

    // Sentinel fill — uses WSCellPool layout. Sets a non-zero
    // fingerprint (= slotIdx + 1, so the wsCellPoolIsEmpty test in Step 3
    // can distinguish "filled" from "empty initial state") and a single
    // dummy candidate at index 0 to verify per-slot writes work.
    WSCellPool p = wsCellPoolInit(slotIdx + 1u);   // non-zero fingerprint
    p.count               = 1u;
    p.lightTypeIndex[0]   = slotIdx;       // recognizable: slot index in light-type field
    p.payload[0]          = slotIdx * 7u;  // recognizable: slot * 7 in payload
    p.sourcePdf[0]        = float(slotIdx) / float(max(poolSize, 1u));
    gPathTracer.lightPool[slotIdx] = p;
}
