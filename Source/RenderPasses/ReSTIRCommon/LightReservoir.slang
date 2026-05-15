/***************************************************************************
 # LightReservoir.slang — DI-lineage shared infrastructure.
 #
 # Hosts the LightSampleDI type (base LightSample + light-identity fields
 # used by reservoir reuse) and the three rebuilder functions that re-
 # materialise a LightSampleDI at a new shading point from a compact
 # stored payload.
 #
 # Consumers: ReSTIRDIPass, ReSTIRDIReferencePass, ReSTIRNEEPass.
 # PathTracerX uses the bare LightSample from PathTraceCore.slang instead
 # (no reservoir reuse → no need for identity fields).
 #
 # Future: when VisCache is split (per project_viscache_three_way_split),
 # this module's contents will migrate to the planned "ReSTIRUtils" /
 # "ReSTIRCommon" plugin alongside the Reservoir struct + RIS primitives.
 *************************************************************************/

import RenderPasses.PathTraceCommon.PathTraceCore;
import RenderPasses.ReSTIRCommon.Reservoir;  // pack/unpack helpers for light-identity payloads
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

/** LightSample variant for the DI lineage — adds light-identity fields used
    by reservoir reuse to re-evaluate Li from a different shading point.

    For LightType::Emissive: lightIndex = active triangle index, lightUV = barys.
    For LightType::Analytic: lightIndex = analytic light index, lightUV = unused.
    For LightType::EnvMap:   lightIndex = 0,                    lightUV = unused (dir carries the identity).
*/
struct LightSampleDI : ILightSampleBase
{
    float3 Li;          ///< Incident radiance at the shading point (unshadowed), already divided by pdf.
    float  pdf;         ///< Pdf with respect to solid angle at the shading point.
    float3 origin;      ///< Ray origin for visibility evaluation.
    float  distance;    ///< Ray distance for visibility evaluation.
    float3 dir;         ///< Ray direction (normalized).
    uint   lightType;   ///< LightType casted to uint.
    uint   lightIndex;  ///< Light identity (per-type meaning above).
    float2 lightUV;     ///< Surface parameterization (per-type meaning above).

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
// Light-sample rebuilders — re-materialise a LightSampleDI at a new shading
// point from a compact stored payload. Used by reservoir reuse to re-evaluate
// candidates at the current pixel.
// ---------------------------------------------------------------------------

/** Re-materialise an env-map LightSampleDI from an oct-packed direction. */
bool coreRebuildEnvMapLightSample(uint payload, const ShadingData sd, EnvMapSampler envMapSampler, out LightSampleDI ls)
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

/** Re-materialise an analytic-light LightSampleDI at a different shading point.
    The cell's stored identity is the lightIndex itself — sampleLight() is
    called from the current pixel against the same light.
*/
bool coreRebuildAnalyticLightSample(uint lightIndex, const ShadingData sd, inout SampleGenerator sg, out LightSampleDI ls)
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

/** Re-materialise an emissive-triangle LightSampleDI from stored (triangleIndex, uv).
    Uses the actual emissive sampler's pdf so MIS weights stay correct.
*/
bool coreRebuildEmissiveLightSample(uint triangleIndex, float2 u, const ShadingData sd, EmissiveLightSampler emissiveSampler, out LightSampleDI ls)
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


// Pack a LightSampleDI's surface payload to the 32-bit reservoir slot.
//   Emissive: barys (16:16 unorm via packUV).
//   EnvMap:   oct-packed direction (16:16) — direction carries the identity.
//   Analytic: 0 (lightIndex carries identity, no surface UV).
uint packLightSamplePayload(LightSampleDI inLs)
{
    if (inLs.lightType == (uint)LightType::Emissive) return packUV(inLs.lightUV);
    if (inLs.lightType == (uint)LightType::EnvMap)   return packDirOct(inLs.dir);
    return 0u;
}
