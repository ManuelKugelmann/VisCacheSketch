/***************************************************************************
 # PathTraceCore.slang — shared path-tracing primitives for VisCacheSketch.
 #
 # Imported by PathTracerX, ReSTIRDIPass, ReSTIRDIReferencePass, ReSTIRNEEPass,
 # ReSTIRPTPass. Lives in a render-pass plugin (Common) that registers no
 # pass class — it exists purely to deploy this slang utility module under
 # runtime/shaders/RenderPasses/Common/ for cross-plugin import.
 #
 # Phase 3d Step 1 (current): LightType + LightSample types + the three
 # light-sample rebuilders that re-materialise a LightSample at a new
 # shading point from a compact stored payload (used by reservoir reuse).
 # Free functions taking samplers as parameters; consumer plugins drop
 # their nested LightType/LightSample/rebuild* declarations and import
 # this module instead.
 *************************************************************************/

import Scene.Scene;
import Scene.ShadingData;
import Rendering.Lights.EnvMapSampler;
import Rendering.Lights.EmissiveLightSampler;
import Rendering.Lights.EmissiveLightSamplerHelpers;
import Rendering.Lights.LightHelpers;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;
import Utils.Geometry.GeometryHelpers;
#include "Utils/Math/MathConstants.slangh"  // FLT_MIN

/** Types of samplable lights. */
enum class LightType
{
    EnvMap,
    Emissive,
    Analytic
};

/** Describes a light sample.

    Layout matches what the plugin's nested `struct PathTracer::LightSample`
    used to define; lifting it to namespace level here so the rebuilders
    below can live as free functions consumable by every plugin.
*/
struct LightSample
{
    float3  Li;         ///< Incident radiance at the shading point (unshadowed), already divided by pdf.
    float   pdf;        ///< Pdf with respect to solid angle at the shading point.
    float3  origin;     ///< Ray origin for visibility evaluation (offsetted to avoid self-intersection).
    float   distance;   ///< Ray distance for visibility evaluation (shortened to avoid self-intersection).
    float3  dir;        ///< Ray direction for visibility evaluation (normalized).
    uint    lightType;  ///< Light type this sample comes from (LightType casted to uint).
    // Identity fields populated by sample generators; consumed by reservoir
    // re-evaluation when rebuilding a LightSample from a different shading point.
    // For LightType::Emissive: lightIndex = active triangle index, lightUV = barys.
    // For LightType::Analytic: lightIndex = analytic light index, lightUV = unused.
    // For LightType::EnvMap:   lightIndex = 0,                    lightUV = unused (dir carries the identity).
    uint    lightIndex;
    float2  lightUV;

    Ray getVisibilityRay() { return Ray(origin, dir, 0.f, distance); }
};

// ---------------------------------------------------------------------------
// Light-type selection probabilities — uniform across the active light kinds.
// kUseEnvLight / kUseEmissiveLights / kUseAnalyticLights are picked up from
// the consumer plugin's USE_*_LIGHT compile-time defines.
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

// Compact light-identity pack/unpack helpers live in VisCache.Reservoir
// (already imported by all reservoir-aware plugins). Common does not
// duplicate them — that creates ambiguous-call errors in slang.

static const float kRayTMaxCore = 1e30f;

// Forward declarations so the rebuilders below can call them without pulling
// in `VisCache.Reservoir` ourselves (Common stays independent of VisCache).
// Defined in `RenderPasses.VisCache.Reservoir` and resolved at link time.
import RenderPasses.VisCache.Reservoir;

// ---------------------------------------------------------------------------
// Light-sample rebuilders — re-materialise a LightSample at a new shading
// point from a compact stored payload. Used by reservoir reuse to re-evaluate
// candidates at the current pixel.
// ---------------------------------------------------------------------------

/** Re-materialise an env-map LightSample from a packed direction.
    `dir` carries the identity (oct-packed in payload).
*/
bool coreRebuildEnvMapLightSample(uint payload, const ShadingData sd, EnvMapSampler envMapSampler, out LightSample ls)
{
    ls = {};
#if USE_ENV_LIGHT == 0
    return false;
#else
    float3 dir = unpackDirOct(payload);
    float pdf = envMapSampler.evalPdf(dir);
    if (pdf <= 0.f) return false;

    float3 Le = gScene.envMap.eval(dir);
    ls.dir       = dir;
    ls.distance  = kRayTMaxCore;
    ls.origin    = computeRayOrigin(sd.posW, dot(sd.faceN, dir) >= 0.f ? sd.faceN : -sd.faceN);
    ls.Li        = Le / pdf;
    ls.pdf       = pdf;
    ls.lightType = (uint)LightType::EnvMap;
    ls.lightIndex = 0u;
    ls.lightUV    = float2(0.f);

    float envSel = coreGetEnvMapSelectionProbability();
    if (envSel <= 0.f) return false;
    ls.pdf *= envSel;
    ls.Li  /= envSel;

    return any(ls.Li > 0.f);
#endif
}

/** Re-materialise an analytic-light LightSample at a different shading point.
    The cell's stored identity is the lightIndex itself — sampleLight() is
    called from the current pixel against the same light.
*/
bool coreRebuildAnalyticLightSample(uint lightIndex, const ShadingData sd, inout SampleGenerator sg, out LightSample ls)
{
    ls = {};
#if USE_ANALYTIC_LIGHTS == 0
    return false;
#else
    uint lightCount = gScene.getLightCount();
    if (lightCount == 0u || lightIndex >= lightCount) return false;

    AnalyticLightSample lightSample;
    if (!sampleLight(sd.posW, gScene.getLight(lightIndex), sg, lightSample)) return false;

    ls.pdf = lightSample.pdf / float(lightCount);
    ls.Li  = lightSample.Li  * float(lightCount);

    float3 normalForOffset = (dot(sd.faceN, lightSample.dir) >= 0.f) ? sd.faceN : -sd.faceN;
    ls.origin     = computeRayOrigin(sd.posW, normalForOffset);
    ls.distance   = lightSample.distance;
    ls.dir        = lightSample.dir;
    ls.lightType  = (uint)LightType::Analytic;
    ls.lightIndex = lightIndex;
    ls.lightUV    = float2(0.f);

    float analyticSel = coreGetAnalyticSelectionProbability();
    if (analyticSel <= 0.f) return false;
    ls.pdf *= analyticSel;
    ls.Li  /= analyticSel;

    return any(ls.Li > 0.f);
#endif
}

/** Re-materialise an emissive-triangle LightSample from stored (triangleIndex, uv).
    Uses the actual emissive sampler's pdf so MIS weights stay correct.
*/
bool coreRebuildEmissiveLightSample(uint triangleIndex, float2 u, const ShadingData sd, EmissiveLightSampler emissiveSampler, out LightSample ls)
{
    ls = {};
#if USE_EMISSIVE_LIGHTS == 0
    return false;
#else
    if (triangleIndex >= gScene.lightCollection.getActiveTriangleCount()) return false;

    EmissiveTriangle tri = gScene.lightCollection.getTriangle(triangleIndex);
    float3 bary = sample_triangle(u);
    float3 lightPosW = tri.getPosition(bary);
    float3 lightOffsetPosW = computeRayOrigin(lightPosW, tri.normal);

    float3 normalForOffset = (dot(sd.faceN, lightOffsetPosW - sd.posW) >= 0.f) ? sd.faceN : -sd.faceN;
    ls.origin = computeRayOrigin(sd.posW, normalForOffset);

    float3 toLight = lightOffsetPosW - ls.origin;
    float distSqr = max(FLT_MIN, dot(toLight, toLight));
    float dist = sqrt(distSqr);
    float3 dir = toLight / dist;

    float cosTheta = dot(tri.normal, -dir);
    if (cosTheta <= 0.f) return false;

    float2 texCoord = tri.getTexCoord(bary);
    float3 Le = gScene.materials.evalEmissive(tri.materialID, texCoord);
    if (gScene.materials.hasLightProfile(tri.materialID))
        Le *= gScene.materials.evalLightProfile(cosTheta);

    TriangleLightHit hit;
    hit.triangleIndex = triangleIndex;
    hit.posW = lightPosW;
    hit.normalW = tri.normal;
    float emPdf = emissiveSampler.evalPdf(sd.posW, sd.faceN, /*upperHemisphere=*/true, hit);
    if (emPdf <= 0.f) return false;

    float emissiveSel = coreGetEmissiveSelectionProbability();
    if (emissiveSel <= 0.f) return false;

    float totalPdf = emPdf * emissiveSel;
    ls.Li         = Le / totalPdf;
    ls.pdf        = totalPdf;
    ls.dir        = dir;
    ls.distance   = dist;
    ls.lightType  = (uint)LightType::Emissive;
    ls.lightIndex = triangleIndex;
    ls.lightUV    = u;

    return any(ls.Li > 0.f);
#endif
}
