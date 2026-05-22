/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/
import Scene.Raytracing;
import Utils.Debug.PixelDebug;
import Rendering.Utils.PixelStats;
import PathTracer;
import PathState;
import Params;
import PathReservoir;

ParameterBlock<PathTracer> gPathTracer;

cbuffer CB
{
    int gSampleId;
}

void walkPath(inout PathState path)
{
    while (path.isActive())
    {
        if (path.isHit())
        {
            gPathTracer.handleHit(path);
            if (path.isTerminated()) break;
            gPathTracer.nextVertex(path);
        }
        else
        {
            gPathTracer.handleMiss(path);
        }
    }
}

void tracePath(uint pathID, inout PathReservoir giReservoir, uint sampleIdx)
{
    PathState path;
    gPathTracer.generatePath(pathID, path);

    printSetPixel(path.getPixel());
    logSetPixel(path.getPixel());

    walkPath(path);

    gPathTracer.finalize(path);
    gPathTracer.writeOutput(path, giReservoir, sampleIdx);
}

[shader("compute")]
// [Slang 2024.14] Newer Slang demands explicit 'vertex' capability for compute
// shaders that touch vertex buffers via Scene methods.
[require(compute, sm_6_6, GL_NV_compute_shader_derivatives, GL_KHR_shader_subgroup_basic, GL_NV_shader_subgroup_partitioned)]
[numthreads(16, 16, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (all(pixel >= gPathTracer.params.frameDim)) return;

    // Skip pixel if there is no hit in the vbuffer.
    HitInfo hit = HitInfo(gPathTracer.vbuffer[pixel]);
    if (!hit.isValid()) return;

    PathReservoir giReservoir;

    static const uint itersPerShaderPass = PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing ? kSamplesPerPixel : kCandidateSamples;

    if (itersPerShaderPass == 1)
    {
        // Handle fixed 1 spp case.
        uint pathID = pixel.x | (pixel.y << 12) | (gSampleId << 24);
        tracePath(pathID, giReservoir, 0);
    }
    else//(itersPerShaderPass > 1)
    {
        // Handle fixed multiple spp case.
        for (uint sampleIdx = 0; sampleIdx < itersPerShaderPass; ++sampleIdx)
        {
            uint pathID = pixel.x | (pixel.y << 12) | (sampleIdx << 24);
            tracePath(pathID, giReservoir, sampleIdx);
        }
    }
}
