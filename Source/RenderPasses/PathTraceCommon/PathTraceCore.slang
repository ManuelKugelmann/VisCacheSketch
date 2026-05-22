/***************************************************************************
 # PathTraceCore.slang — TRULY-COMMON path-tracing primitives.
 #
 # Imported by every consumer that does NEE: PathTracerX, ReSTIRDIPass,
 # ReSTIRDIReferencePass, ReSTIRNEEPass, ReSTIRPTPass (eventually).
 #
 # Contents are lineage-agnostic — anything specific to DI's reservoir-of-
 # light-samples lineage (LightSampleDI + rebuilders) lives in
 # LightReservoir.slang; anything specific to PT's path-reservoir lineage
 # would live in a parallel PathReservoir.slang (not yet present).
 #
 # The base LightSample type here has 6 fields — the minimum every NEE
 # consumer needs. The DI lineage extends it (lightIndex + lightUV) for
 # reservoir reuse identity. The PT lineage extends differently (packedHit
 # + lightNormalW) for path-reservoir reconnection.
 *************************************************************************/

import Scene.Scene;
import Scene.ShadingData;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;
import Utils.Geometry.GeometryHelpers;

/** Types of samplable lights. Shared across DI / PT / future BDPT lineages. */
enum class LightType
{
    EnvMap,
    Emissive,
    Analytic
};

/** MIS heuristic identifier — matches each pass's local MISHeuristic enum
    value-for-value (Balance=0, PowerTwo=1, PowerExp=2). The free function
    below takes a uint so it stays decoupled from any single pass's enum
    type; each caller passes uint(kMISHeuristic). Phase 3 sub-step 3.0 —
    first shared helper extracted from per-pass struct PathTracer copies.

    \param[in] heuristic 0=Balance, 1=PowerTwo, 2=PowerExp.
    \param[in] powerExponent Exponent used only for PowerExp. Other heuristics ignore it.
    \param[in] n0 Number of samples taken from the first sampling strategy.
    \param[in] p0 Pdf for the first sampling strategy.
    \param[in] n1 Number of samples taken from the second sampling strategy.
    \param[in] p1 Pdf for the second sampling strategy.
    \return Weight for the contribution from the first strategy (p0).
*/
float evalMISImpl(uint heuristic, float powerExponent, float n0, float p0, float n1, float p1)
{
    switch (heuristic)
    {
    case 0u: // Balance
    {
        float q0 = n0 * p0;
        float q1 = n1 * p1;
        return q0 / (q0 + q1);
    }
    case 1u: // PowerTwo
    {
        float q0 = (n0 * p0) * (n0 * p0);
        float q1 = (n1 * p1) * (n1 * p1);
        return q0 / (q0 + q1);
    }
    case 2u: // PowerExp
    {
        float q0 = pow(n0 * p0, powerExponent);
        float q1 = pow(n1 * p1, powerExponent);
        return q0 / (q0 + q1);
    }
    default:
        return 0.f;
    }
}

/** Common-base interface: the six fields every NEE consumer needs.

    Concrete implementers (LightSample here, LightSampleDI in LightReservoir.slang,
    future LightSamplePT) declare the fields directly and provide trivial
    accessor bodies; the interface lets generic functions in this module
    operate on any LightSample variant. (Slang doesn't support C++-style
    struct inheritance; interfaces are how we share method-shape across
    concrete structs with overlapping field layouts.)
*/
interface ILightSampleBase
{
    [mutating] void setBase(float3 Li, float pdf, float3 origin, float distance,
                            float3 dir, uint lightType);
    float3 getLi();
    float  getPdf();
    float3 getOrigin();
    float  getDistance();
    float3 getDir();
    uint   getLightType();
    Ray    getVisibilityRay();
};

/** Base LightSample with only the 6 fields every consumer reads.

    Used directly by PathTracerX (the forward path tracer — no reservoir reuse,
    so the lineage-specific identity/reconnection fields are dead weight).
    ReSTIR DI plugins use LightSampleDI (in LightReservoir.slang) instead.
*/
struct LightSample : ILightSampleBase
{
    float3 Li;          ///< Incident radiance at the shading point (unshadowed), already divided by pdf.
    float  pdf;         ///< Pdf with respect to solid angle at the shading point.
    float3 origin;      ///< Ray origin for visibility evaluation (offsetted to avoid self-intersection).
    float  distance;    ///< Ray distance for visibility evaluation (shortened to avoid self-intersection).
    float3 dir;         ///< Ray direction for visibility evaluation (normalized).
    uint   lightType;   ///< Light type this sample comes from (LightType casted to uint).

    [mutating] void setBase(float3 Li_, float pdf_, float3 origin_, float distance_,
                            float3 dir_, uint lightType_)
    { Li = Li_; pdf = pdf_; origin = origin_; distance = distance_; dir = dir_; lightType = lightType_; }
    float3 getLi()        { return Li; }
    float  getPdf()       { return pdf; }
    float3 getOrigin()    { return origin; }
    float  getDistance()  { return distance; }
    float3 getDir()       { return dir; }
    uint   getLightType() { return lightType; }
    Ray    getVisibilityRay() { return Ray(origin, dir, 0.f, distance); }
};

// ---------------------------------------------------------------------------
// Light-type selection probabilities — uniform across active light kinds.
// USE_ENV_LIGHT / USE_EMISSIVE_LIGHTS / USE_ANALYTIC_LIGHTS are picked up
// from the consumer plugin's compile-time defines.
// ---------------------------------------------------------------------------

float coreGetEnvMapSelectionProbability()
{
    int numTypes = (USE_ENV_LIGHT != 0 ? 1 : 0)
                 + (USE_EMISSIVE_LIGHTS != 0 ? 1 : 0)
                 + (USE_ANALYTIC_LIGHTS != 0 ? 1 : 0);
    return (USE_ENV_LIGHT != 0 && numTypes > 0) ? (1.f / float(numTypes)) : 0.f;
}

float coreGetEmissiveSelectionProbability()
{
    int numTypes = (USE_ENV_LIGHT != 0 ? 1 : 0)
                 + (USE_EMISSIVE_LIGHTS != 0 ? 1 : 0)
                 + (USE_ANALYTIC_LIGHTS != 0 ? 1 : 0);
    return (USE_EMISSIVE_LIGHTS != 0 && numTypes > 0) ? (1.f / float(numTypes)) : 0.f;
}

float coreGetAnalyticSelectionProbability()
{
    int numTypes = (USE_ENV_LIGHT != 0 ? 1 : 0)
                 + (USE_EMISSIVE_LIGHTS != 0 ? 1 : 0)
                 + (USE_ANALYTIC_LIGHTS != 0 ? 1 : 0);
    return (USE_ANALYTIC_LIGHTS != 0 && numTypes > 0) ? (1.f / float(numTypes)) : 0.f;
}

static const float kRayTMaxCore = 1e30f;
