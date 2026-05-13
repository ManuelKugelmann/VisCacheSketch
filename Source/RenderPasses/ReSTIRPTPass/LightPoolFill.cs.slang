/***************************************************************************
 * LightPoolFill.cs.slang
 *
 * P-axis pool fill pass — STUB. Step 2 of MVP.
 *
 * Per user direction 2026-05-11: shares the CellPool struct from
 * VisCache (see LightPool.slang). For now writes a recognizable sentinel
 * so Step 3 (NEE-site reader-side RIS) can verify slot keying works
 * without yet doing real emissiveSampler.sampleLight at insert.
 *
 * Real implementation TODO:
 *   - mirror CellPoolIO.slang::cellPoolInsert (RIS-at-insert with
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
import RenderPasses.ReSTIRCommon.CellPool;   // direct: slang imports aren't transitive
import Params;

ParameterBlock<PathTracer> gPathTracer;

[numthreads(64, 1, 1)]
void main(uint3 dtid : SV_DispatchThreadID)
{
    const uint slotIdx = dtid.x;
    const uint poolSize = gPathTracer.params.screenTiles.x * gPathTracer.params.screenTiles.y
                          * (kScreenTileDim.x * kScreenTileDim.y);
    if (slotIdx >= max(poolSize, 1u)) return;

    // Sentinel header init — touches only CellPool's top-level fields.
    // The nested slots[] array (1024 × 12 B) is left to the parallel
    // agent's CellPoolIO::cellPoolInsert; this pass just marks the
    // pool as "initialised" via a non-zero fingerprint.
    gPathTracer.lightPool[slotIdx].fingerprint = slotIdx + 1u;
    gPathTracer.lightPool[slotIdx].count       = 0u;
}
