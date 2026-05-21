/** Falcor-8-workaround experiment, attempt 2: copy SpatialReuse's structure
    (wrapper function + guard + Texture2D global + RMIS static const) verbatim
    and see if it reflects clean. If yes, the trip is purely about the WAY
    the body invokes ShiftPath, not what surrounds it.
*/
import PathShift;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;
import Utils.Debug.PixelDebug;

Texture2D<uint4> gShiftProbeVertices;

static const RMISType gShiftProbeMISType = (RMISType)SPATIAL_RMIS_TYPE;

// EXACT mirror of SpatialReuse.cs.slang::SpatialShift — guard wrapper.
PathSample ShiftProbeWrapped(const PathSample basePath, const PackedPathVertex newVertex, out float jacobian) {
    jacobian = 0;
    PathSample result = {};

    if (!basePath.HasFlag(PathFlags::eCausticLightPath)) {
        int2 tmp;
        result = ShiftPath(basePath, newVertex, tmp, jacobian);
    }

    return result;
}

[shader("compute")]
[numthreads(8, 4, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;

    // Mimic SpatialReuse.cs.slang::main's pattern: LoadInputReservoir + LoadPrimaryVertex + guarded ShiftPath via wrapper.
    PathReservoir r = gPathGenerator.LoadInputReservoir(id);
    const PackedPathVertex vertex = gPathGenerator.LoadPrimaryVertex(id);

    float jacobian;
    PathSample shifted = ShiftProbeWrapped(r.mSample, vertex, jacobian);

    gPathGenerator.mOutputRadiance[id] = float4(shifted.IsValid() ? 1 : 0, jacobian, 0, 1);
}
