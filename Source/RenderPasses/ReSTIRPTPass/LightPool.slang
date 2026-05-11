/***************************************************************************
 * LightPool.slang
 *
 * Per-tile / per-cell presampled NEE light-sample pool for P-axis variants
 * (P2d screen-tile / P3d world-cell).
 *
 * Status: STEP 1 OF MVP — struct definition + reflection only. No fill
 * pass, no NEE-site read. The buffer allocates when restirptPoolAddrMode
 * != 0 but is not yet used by any shader code path.
 *
 * Design: see Source/RenderPasses/ReSTIRPTPass/PORT_NOTES_P_AXIS.md
 *
 * Self-contained packed sample representation (decoupled from
 * PathTracer::LightSample) to avoid pulling PathTracer's heavy import
 * tree into the reflection-only TU.
 **************************************************************************/
#pragma once

import Scene.HitInfo;   // for HitInfo (light surface hit)

/// Compile-time number of presampled candidates per pool slot. K=16 is the
/// RTXDI default; gives reasonable variance reduction for K-RIS at NEE
/// without ballooning the pool buffer (~1 KB per slot at K=16).
static const uint kLightPoolK = 16u;

/// Packed light sample stored in the pool. Mirrors the fields needed at
/// the NEE-site read (PathTracer::LightSample); fill pass populates from
/// emissiveSampler.sampleLight + analyticLightSample. ~64 B per sample.
struct PackedLightPoolSample
{
    float3  Li;            ///< Incident radiance at sampling point (already / pdf).
    float   pdf;           ///< Pdf w.r.t. solid angle.
    float3  origin;        ///< Visibility ray origin.
    float   distance;      ///< Visibility ray distance.
    float3  dir;           ///< Visibility ray direction (normalized).
    uint    lightType;     ///< LightSampleType cast to uint.
    HitInfo packedHit;     ///< Light surface hit (for emissive triangles).
    float3  lightNormalW;  ///< Light surface normal at sampled point.
};

/// Per-pool-slot storage. Each slot holds K independent presampled lights
/// drawn by the fill pass (TODO step 2). NEE-site reads will K-RIS over
/// these samples (TODO step 3).
struct LightPoolSlot
{
    PackedLightPoolSample samples[kLightPoolK];
};
