/***************************************************************************
 * LightPoolFill.cs.slang
 *
 * P-axis pool fill pass — Step 2c partial.
 *
 * Reuses gPathTracer's binding (cbuffer "CB" wrapping PathTracer struct)
 * to gain access to scene + emissiveSampler + lightPool buffer without
 * a separate parameter block. Sentinel-fill for now (writes recognizable
 * values so Step 3 can verify slot keying); real emissiveSampler.sampleLight
 * integration is the final piece of Step 2c.
 *
 * Design: see Source/RenderPasses/ReSTIRPTPass/PORT_NOTES_P_AXIS.md
 **************************************************************************/
import Scene.Scene;
import PathTracer;     // pulls EnvMapSampler, EmissiveLightSampler, lightPool field
import LightPool;
import Params;

ParameterBlock<PathTracer> gPathTracer;

[numthreads(64, 1, 1)]
void main(uint3 dtid : SV_DispatchThreadID)
{
    const uint slotIdx = dtid.x;
    const uint poolSize = gPathTracer.params.screenTiles.x * gPathTracer.params.screenTiles.y
                          * (kScreenTileDim.x * kScreenTileDim.y);
    if (slotIdx >= max(poolSize, 1u)) return;

    // Sentinel fill — writes recognizable values for Step 3 verification:
    //   samples[k].Li.x = slotIdx (slot ID lets NEE assert pool keying)
    //   samples[k].pdf  = k/K     (slot-internal index check)
    //
    // Real implementation TODO:
    //   - SampleGenerator sg = SampleGenerator(uint2(slotIdx, gPathTracer.params.frameCount), 0);
    //   - compute proxy shading point per slot (tile-center pixel for P2d,
    //     cell-center world pos for P3d — P3d needs a separate slot->pos
    //     table since cell hashes are one-way)
    //   - for k in [0, kLightPoolK):
    //       LightSample ls;
    //       if (gPathTracer.emissiveSampler.sampleLight(proxyPos, proxyN, true, sg, tls, ls)) {
    //           pack into samples[k]
    //       }
    LightPoolSlot slot;
    [unroll]
    for (uint k = 0; k < kLightPoolK; ++k)
    {
        slot.samples[k].Li = float3(float(slotIdx), 0.0, 0.0);
        slot.samples[k].pdf = float(k) / float(kLightPoolK);
        slot.samples[k].origin = float3(0.0);
        slot.samples[k].distance = 0.0;
        slot.samples[k].dir = float3(0.0);
        slot.samples[k].lightType = 0u;
    }
    gPathTracer.lightPool[slotIdx] = slot;
}
