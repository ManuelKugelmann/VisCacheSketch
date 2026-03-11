/***************************************************************************
 * ReSTIRPTCommon.slang
 *
 * Shared data structures for ReSTIR PT (multi-bounce path reuse).
 * Extends ReSTIRGICommon with prefix throughput and reconnection depth.
 ***************************************************************************/

#pragma once

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;

// ---------------------------------------------------------------------------
// Helper: load ShadingData from HitInfo (Falcor 8.0 standalone pattern).
// ---------------------------------------------------------------------------
ShadingData loadSD(const HitInfo hit, float3 rayOrigin, float3 rayDir)
{
    VertexData v;
    uint materialID = 0;
    if (hit.getType() == HitType::Triangle)
    {
        const TriangleHit tri = hit.getTriangleHit();
        v = gScene.getVertexData(tri);
        materialID = gScene.getMaterialID(tri.instanceID);
    }
    else
    {
        v.posW = rayOrigin + rayDir;
        v.normalW = -rayDir;
        v.faceNormalW = -rayDir;
        v.tangentW = float4(0, 1, 0, 1);
        v.texC = float2(0);
    }
    return gScene.materials.prepareShadingData(v, materialID, -rayDir);
}

// ---------------------------------------------------------------------------
// Firefly clamp threshold (shared across final shading passes)
// ---------------------------------------------------------------------------
static const float kFireflyClamp = 50.0f;

// ---------------------------------------------------------------------------
// Numerical thresholds (named for auditability)
// ---------------------------------------------------------------------------
static const float kLuminanceEps      = 1e-7f;   ///< Min radiance to consider non-zero
static const float kDistanceEps       = 1e-6f;   ///< Min distance to avoid division by zero
static const float kGeomNormalThresh        = 0.9f;    ///< Temporal: dot(N1,N2) threshold
static const float kGeomDepthThresh         = 0.1f;    ///< Temporal: relative depth threshold
static const float kSpatialGeomNormalThresh = 0.5f;    ///< Spatial: looser normal threshold for neighbor selection
static const float kSpatialGeomDepthThresh  = 0.2f;    ///< Spatial: looser depth threshold for neighbor selection
static const float kShadowRayOffset         = 1e-4f;   ///< Ray tMin/tMax offset to avoid self-intersection

// ---------------------------------------------------------------------------
// Secondary bounce hit data — same as GI version
// ---------------------------------------------------------------------------
struct SecondaryHit
{
    float3 posW;
    float3 normalW;
    float3 Lo;
    float  invPDF;
    float3 wi;
    uint   _pad;
};

// ---------------------------------------------------------------------------
// Path reservoir — extended from GI to carry multi-bounce path state.
// DQLin's ReSTIR PT stores a reconnection vertex at a chosen depth.
// ---------------------------------------------------------------------------
struct PathReservoir
{
    SecondaryHit sample;
    float  W;
    float  M;
    float  wSum;
    float  targetPdf;
    float3 prefixThroughput;   ///< Cumulative BSDF*cos product along path prefix
    uint   reconnectDepth;     ///< Bounce depth of the reconnection vertex

    bool isValid() { return M > 0.0f && targetPdf > 0.0f; }

    [mutating] void reset()
    {
        sample.posW    = float3(0);
        sample.normalW = float3(0, 1, 0);
        sample.Lo      = float3(0);
        sample.invPDF  = 0.0f;
        sample.wi      = float3(0);
        sample._pad    = 0u;
        W = 0.0f;
        M = 0.0f;
        wSum = 0.0f;
        targetPdf = 0.0f;
        prefixThroughput = float3(1.0f);
        reconnectDepth   = 0u;
    }

    [mutating] bool update(SecondaryHit newSample, float weight, float newTargetPdf,
                           float3 prefix, uint depth, inout SampleGenerator sg)
    {
        M    += 1.0f;
        wSum += weight;
        if (sampleNext1D(sg) * wSum < weight)
        {
            sample           = newSample;
            targetPdf        = newTargetPdf;
            prefixThroughput = prefix;
            reconnectDepth   = depth;
            return true;
        }
        return false;
    }

    [mutating] bool merge(PathReservoir other, float otherTargetPdfAtThis,
                          inout SampleGenerator sg)
    {
        float weight = otherTargetPdfAtThis * other.W * other.M;
        M    += other.M;
        wSum += weight;
        if (wSum > 0.0f && sampleNext1D(sg) * wSum < weight)
        {
            sample           = other.sample;
            targetPdf        = otherTargetPdfAtThis;
            prefixThroughput = other.prefixThroughput;
            reconnectDepth   = other.reconnectDepth;
            return true;
        }
        return false;
    }

    [mutating] void finalize()
    {
        W = (M > 0.0f && targetPdf > 0.0f) ? (wSum / (M * targetPdf)) : 0.0f;
    }
};

// Target function
float evalTargetPdf(float3 bsdf, float3 Lo, float G)
{
    return max(luminance(bsdf * Lo * G), 0.0f);
}

// Geometry similarity check
bool geometryValid(float3 N1, float3 N2, float3 P1, float3 P2,
                   float normalThresh, float depthThresh)
{
    if (dot(N1, N2) < normalThresh) return false;
    float dist = length(P1 - P2);
    float maxDepth = max(length(P1), length(P2));
    if (dist > depthThresh * maxDepth) return false;
    return true;
}

static const float kMaxTemporalM = 20.0f;
static const float kMaxSpatialM  = 500.0f;
