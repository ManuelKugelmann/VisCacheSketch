/***************************************************************************
 * ReSTIRGICommon.slang
 *
 * Shared data structures and utilities for ReSTIR GI pass.
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 → 8.0).
 *
 * PathReservoir: streaming weighted reservoir for path reuse.
 * SecondaryHit: secondary bounce data (reconnection vertex).
 ***************************************************************************/

#pragma once

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;

// ---------------------------------------------------------------------------
// Helper: load ShadingData from HitInfo (Falcor 8.0 standalone pattern).
// Falcor 8.0's loadShadingData lives in PathTracer/LoadShadingData.slang;
// we inline the core logic here to avoid coupling to PathTracer internals.
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
        // Non-triangle fallback (curves, SDF, etc.) — not expected in GI pass
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
// Secondary bounce hit data — stored per pixel, reused across frames/neighbors
// ---------------------------------------------------------------------------
struct SecondaryHit
{
    float3 posW;        ///< World-space hit position
    float3 normalW;     ///< World-space shading normal at hit
    float3 Lo;          ///< Outgoing radiance at hit (includes emission + indirect)
    float  invPDF;      ///< 1/pdf of the sampling direction
    float3 wi;          ///< Incident direction (from shading point to hit)
    uint   _pad;
};

// ---------------------------------------------------------------------------
// Streaming weighted reservoir [Talbot et al. 2005 / Bitterli et al. 2020]
// ---------------------------------------------------------------------------
struct PathReservoir
{
    SecondaryHit sample;    ///< Selected sample
    float  W;               ///< Unbiased contribution weight = (1/targetPdf) * (wSum/M)
    float  M;               ///< Number of candidates seen so far
    float  wSum;            ///< Running sum of weights
    float  targetPdf;       ///< Target function p_hat evaluated at selected sample

    bool isValid() { return M > 0.0f && targetPdf > 0.0f; }

    /// Reset to empty
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
    }

    /// Stream one candidate into the reservoir.
    /// Returns true if this candidate was selected.
    [mutating] bool update(SecondaryHit newSample, float weight, float newTargetPdf,
                           inout SampleGenerator sg)
    {
        M    += 1.0f;
        wSum += weight;
        if (sampleNext1D(sg) * wSum < weight)
        {
            sample    = newSample;
            targetPdf = newTargetPdf;
            return true;
        }
        return false;
    }

    /// Merge another reservoir into this one (streaming RIS).
    /// otherTargetPdf = target function at other's selected sample evaluated at THIS pixel.
    [mutating] bool merge(PathReservoir other, float otherTargetPdfAtThis,
                          inout SampleGenerator sg)
    {
        float weight = otherTargetPdfAtThis * other.W * other.M;
        M    += other.M;
        wSum += weight;
        if (wSum > 0.0f && sampleNext1D(sg) * wSum < weight)
        {
            sample    = other.sample;
            targetPdf = otherTargetPdfAtThis;
            return true;
        }
        return false;
    }

    /// Finalize W after all candidates have been streamed.
    [mutating] void finalize()
    {
        W = (M > 0.0f && targetPdf > 0.0f) ? (wSum / (M * targetPdf)) : 0.0f;
    }
};

// ---------------------------------------------------------------------------
// Target function p_hat for ReSTIR GI: luminance of the unshadowed contribution.
// This is the reconnection-based target function from DQLin.
// ---------------------------------------------------------------------------
float evalTargetPdf(float3 bsdf, float3 Lo, float G)
{
    return max(luminance(bsdf * Lo * G), 0.0f);
}

// ---------------------------------------------------------------------------
// Geometry similarity check for temporal/spatial reuse validity
// ---------------------------------------------------------------------------
bool geometryValid(float3 N1, float3 N2, float3 P1, float3 P2, float normalThresh, float depthThresh)
{
    // Normal check
    if (dot(N1, N2) < normalThresh) return false;
    // Depth / position proximity check (relative)
    float dist = length(P1 - P2);
    float maxDepth = max(length(P1), length(P2));
    if (dist > depthThresh * maxDepth) return false;
    return true;
}

// ---------------------------------------------------------------------------
// M-cap for temporal stability [Bitterli et al. 2020]
// Prevents temporal reservoirs from accumulating unbounded history.
// ---------------------------------------------------------------------------
static const float kMaxTemporalM = 20.0f;
static const float kMaxSpatialM  = 500.0f;
