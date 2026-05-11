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

    void execute(uint slotIdx)
    {
        if (slotIdx >= poolSize) return;
        // STUB: zero out the slot. Real impl draws K candidates from
        // emissiveSampler. The zeroed Li=0/pdf=0 values will not
        // contribute to RIS at the NEE-site read, so this stub is safe
        // (NEE will fall back to fresh sampling per Pno).
        LightPoolSlot slot;
        for (uint k = 0; k < kLightPoolK; ++k)
        {
            slot.samples[k].Li = float3(0.0);
            slot.samples[k].pdf = 0.0;
            slot.samples[k].origin = float3(0.0);
            slot.samples[k].distance = 0.0;
            slot.samples[k].dir = float3(0.0);
            slot.samples[k].lightType = 0u;
            // packedHit + lightNormalW: leave default-init.
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
