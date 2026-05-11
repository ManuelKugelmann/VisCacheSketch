/***************************************************************************
 * LightPoolFill.cs.slang
 *
 * P-axis pool fill pass — STUB. Step 2 of 3 in P-axis MVP (Task #21).
 *
 * Compiles + dispatches if wired in by host but does no useful work yet
 * (writes zeroed PackedLightPoolSamples). Use this as the starting point
 * for the real fill implementation.
 *
 * Design: see Source/RenderPasses/ReSTIRPTPass/PORT_NOTES_P_AXIS.md.
 *
 * Real implementation (TODO):
 *   - import Rendering.Lights.EmissiveLightSampler + EnvMapSampler
 *   - construct SampleGenerator with slot-keyed seed (deterministic per
 *     slot per frame; e.g. pcg(slotIdx ^ frameCount))
 *   - for k in [0, kLightPoolK): call emissiveSampler.sampleLight at a
 *     proxy shading point (slot-cell-center for P3d, screen-tile-center
 *     for P2d) and pack the resulting LightSample into samples[k]
 *   - host: insert dispatch BEFORE TracePass, ONCE per frame (not per
 *     ReSTIR iter), gated on params.restirptPoolAddrMode != 0
 **************************************************************************/
import LightPool;

struct LightPoolFiller
{
    RWStructuredBuffer<LightPoolSlot> lightPool;
    uint poolSize;     ///< Number of slots to fill (= mpLightPool->getElementCount())
    uint frameCount;   ///< For temporal seeding when real sampler is wired in (TODO).

    void execute(uint slotIdx)
    {
        if (slotIdx >= poolSize) return;
        // STUB: writes a recognizable sentinel value so the NEE-site read
        // (Step 3) can verify the pool actually persists between fill-pass
        // and main TracePass without yet sampling real lights:
        //   samples[k].Li.x = slotIdx (slot ID, lets NEE assert pool is keyed correctly)
        //   samples[k].pdf  = float(k) / kLightPoolK  (slot-internal index check)
        //
        // Real implementation TODO (Step 2c):
        //   - import Rendering.Lights.EmissiveLightSampler + EnvMapSampler
        //   - bind emissiveSampler/envMapSampler on this struct (separate
        //     from PathTracer's bindings, OR share via mpPathTracerBlock)
        //   - SampleGenerator sg = SampleGenerator(uint2(slotIdx, frameCount), 0);
        //   - compute proxy shading point:
        //       P2d: tile-center pixel -> primary ray -> hit.posW
        //       P3d: invert cell hash -> cell-center world pos (requires
        //            a separate slotIdx -> worldPos table, since cell
        //            hashes are one-way; populated by writeCentralReservoir)
        //   - for k in [0, kLightPoolK): emissiveSampler.sampleLight(...)
        //     -> pack into PackedLightPoolSample
        LightPoolSlot slot;
        for (uint k = 0; k < kLightPoolK; ++k)
        {
            slot.samples[k].Li = float3(float(slotIdx), 0.0, 0.0);
            slot.samples[k].pdf = float(k) / float(kLightPoolK);
            slot.samples[k].origin = float3(0.0);
            slot.samples[k].distance = 0.0;
            slot.samples[k].dir = float3(0.0);
            slot.samples[k].lightType = 0u;
        }
        lightPool[slotIdx] = slot;
    }
};

cbuffer CB
{
    LightPoolFiller gFiller;
}

[numthreads(64, 1, 1)]
void main(uint3 dtid : SV_DispatchThreadID)
{
    gFiller.execute(dtid.x);
}
