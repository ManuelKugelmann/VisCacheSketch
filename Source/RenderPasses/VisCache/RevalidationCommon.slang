/***************************************************************************
 * RevalidationCommon.slang
 *
 * Shared CV+RRR revalidation logic for all ReSTIR variants (GI, PT).
 *
 * This module provides a 3-way dispatcher for visibility evaluation during
 * spatial/temporal reuse. The three paths allow clean A/B comparison
 * between VisCache, reservoir-local, and vanilla (unconditional) approaches:
 *
 *   USE_VISCACHE_VISIBILITYCHECK:  VisCache hash table CV+RRR (§12)
 *     - Uses the global spatial hash table for visibility estimates
 *     - Best ray savings: leverages cached visibility across all pixels
 *     - Requires VisCache pass upstream in the render graph
 *
 *   USE_LOCAL_CVRRR:  Reservoir-local CV+RRR (ablation baseline)
 *     - No hash table — derives mu from reservoir-local information only
 *     - mu = clamp(neighborTargetPdf / pHatNoVis, 0, 1)
 *     - Less effective than VisCache (no spatial sharing), but zero memory cost
 *     - Useful for ablation: "how much does the hash table add vs. just RR?"
 *
 *   Neither:  Vanilla unconditional shadow ray
 *     - Always traces — baseline for measuring ray savings
 *
 * Expects the importing file to define before import:
 *   float traceVisibilityRay(float3 origin, float3 target) → 0.0 or 1.0
 *   float traceShadowRay(float3 origin, float3 target) → 0.0 or 1.0
 ***************************************************************************/

import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.ShadingCV;

// ===========================================================================
// LOCAL CV+RRR (ABLATION BASELINE — NO HASH TABLE)
// ===========================================================================

// ---------------------------------------------------------------------------
// LocalRevalCB: parameters for the local revalidation ablation path.
// Bound by the host (ReSTIRPTPass.cpp) when USE_LOCAL_CVRRR=1.
//
// gLocalRevalContribThreshold: contribution luminance above which pMin is
//   raised (firefly suppression). Same concept as gFireflyBudget in VisCache.
//
// gLocalRevalPMin: minimum RR survival probability. Same as gPMin.
// ---------------------------------------------------------------------------
#if USE_LOCAL_CVRRR
cbuffer LocalRevalCB
{
    float gLocalRevalContribThreshold;  ///< Firefly budget for local reval
    float gLocalRevalPMin;              ///< Min RR survival probability
};
#endif

// ---------------------------------------------------------------------------
// evalLocalRevalidation: CV+RRR using reservoir-local visibility estimate.
//
// Instead of looking up a hash table, we derive the visibility estimate mu
// from information already available in the reservoir:
//
//   mu = clamp(neighborTargetPdf / pHatNoVis, 0, 1)
//
// Reasoning: the neighbor's targetPdf was computed in a prior pass WITH
// visibility (it's zero for occluded paths). pHatNoVis is the same target
// function WITHOUT visibility (always > 0 for valid paths). Their ratio
// approximates the visibility that was baked into the neighbor's reservoir.
//
// This is less accurate than VisCache (it only knows about this specific
// reservoir, not all nearby rays), but it requires zero additional memory
// and provides a useful ablation baseline to measure the hash table's value.
//
// The CV+RRR estimator is the same as VisCache:
//   E[mu + (V - mu) / p] = E[V], unbiased for any p in (0,1].
// ---------------------------------------------------------------------------
float evalLocalRevalidation(float3 P, float3 Q, float3 bsdf, float3 Lo,
                             float G, float neighborTargetPdf, float pHatNoVis,
                             float contribThreshold, float pMin,
                             inout SampleGenerator sg)
{
    // Derive visibility estimate from reservoir data.
    static const float kLumEps = 1e-7f;
    float mu = (pHatNoVis > kLumEps) ? clamp(neighborTargetPdf / pHatNoVis, 0.0f, 1.0f)
                                     : 0.5f;  // No data → uncertain (max variance)

    // Contribution-weighted residual bound: same as VisCache's firefly logic.
    // High-contribution edges get higher p to prevent weight explosion.
    float3 C   = bsdf * Lo * G;
    float  res = luminance(C) * max(mu, 1.0f - mu);
    float  p   = clamp(res / contribThreshold, pMin, 1.0f);

    // RR coin flip: trace with probability p, skip with probability 1-p.
    if (sampleNext1D(sg) < p)
    {
        float V = traceShadowRay(P, Q);
        return mu + (V - mu) / p;  // Unbiased CV+RRR estimator
    }
    return mu;  // No trace — use reservoir-local estimate
}

// ===========================================================================
// 3-WAY DISPATCHER
// ===========================================================================

// ---------------------------------------------------------------------------
// evaluateVisibility: dispatches to the appropriate visibility evaluation
// method based on compile-time flags.
//
// This is the single entry point that all ReSTIR spatial/temporal reuse
// code should call. The compile flags determine which path is taken at
// shader compile time, allowing clean A/B ablation without runtime overhead.
//
// Parameters:
//   P, Q: endpoints of the visibility query (primary hit, reconnection vertex)
//   bsdf, Lo, G: path throughput components for contribution-aware RR
//   neighborTargetPdf, pHatNoVis: reservoir-local data (only used by local reval)
//   camPos: legacy parameter (now unused, kept for API compatibility)
//   sg: sample generator for RR coin flips
//
// Returns: visibility weight in [0, 1], unbiased estimate of V(P, Q).
// ---------------------------------------------------------------------------
float evaluateVisibility(float3 P, float3 Q, float3 bsdf, float3 Lo,
                          float G, float neighborTargetPdf, float pHatNoVis,
                          float3 camPos, inout SampleGenerator sg)
{
#if USE_VISCACHE_VISIBILITYCHECK
    // VisCache hash table CV+RRR (§12).
    // Best ray savings — leverages spatial sharing across all pixels.
    return evalRevalidationCV(P, Q, bsdf, Lo, G, sg);
#elif USE_LOCAL_CVRRR
    // Reservoir-local CV+RRR — no hash table, ablation baseline.
    return evalLocalRevalidation(P, Q, bsdf, Lo, G, neighborTargetPdf, pHatNoVis,
                                  gLocalRevalContribThreshold, gLocalRevalPMin, sg);
#else
    // Vanilla: unconditional shadow ray for each neighbor.
    // Baseline for measuring ray savings.
    return traceShadowRay(P, Q);
#endif
}
