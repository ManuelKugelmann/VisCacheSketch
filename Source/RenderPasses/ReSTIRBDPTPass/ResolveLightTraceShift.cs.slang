/** Falcor-8-workaround experiment: clone of BDPT.cs.slang::ResolveLightTraceReservoirs
    into a separate compute file, WITH the ShiftPath branch enabled. Tests whether
    putting the resolve entry in its own .cs.slang file bypasses the reflection trip
    that hits BDPT.cs.slang::ResolveLightTraceReservoirs.

    Hypothesis: SpatialReuse.cs.slang's main entry calls ShiftPath fine; ResolveLightTraceReservoirs
    crashes. The difference might be call-graph shape SPECIFIC to BDPT.cs.slang. Moving the
    entry to its own file separates it.
*/
import Utils.Color.ColorMap;
import Utils.Sampling.SampleGenerator;
import Utils.Debug.PixelDebug;
import PathShift;

static const bool gUseCausticReservoirs   = USE_CAUSTIC_RESERVOIRS;

// EXPERIMENTAL: minimal repro test — call ShiftPath but DON'T read from
// mLightTraceReservoirs. If this passes setVars where the full resolve
// crashes, the trigger is the combo of HashMap-subscript + ShiftPath.
// Test: trivial entry that does NOTHING but write a constant. If THIS
// crashes setVars, the issue is "additional compute pass exceeds Falcor 8
// reflection threshold". If it passes, the issue is content of the body.
[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;

    PathSample basePath = {};
    PackedPathVertex pv = {};
    int2 tmp;
    float jacobian;
    PathSample result = ShiftPath(basePath, pv, tmp, jacobian);
    gPathGenerator.mOutputRadiance[id] = float4(result.IsValid() ? 1 : 0, jacobian, 0, 1);
}
