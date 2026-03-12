/***************************************************************************
 * RevalidationCommon.slang
 *
 * Shared CV+RRR revalidation logic used by all ReSTIR variants (GI, PT).
 *
 * Provides:
 *   - evalLocalRevalidation(): reservoir-local mu CV+RRR (no hash table)
 *   - evaluateVisibility():    3-way dispatcher (VisCache / local / vanilla)
 *
 * Expects the importing file to define before import:
 *   - traceVisibilityRay(float3 origin, float3 target) -> float
 *   - traceShadowRay(float3 origin, float3 target) -> float
 *
 * Compile defines:
 *   USE_VISCACHE_REVAL=1: VisCache hash table CV+RRR (S11.3)
 *   USE_LOCAL_REVAL=1:    reservoir-local CV+RRR (ablation baseline)
 *   Neither:              vanilla unconditional shadow ray
 ***************************************************************************/

import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

#if USE_VISCACHE
import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.ShadingCV;
#endif

// ---------------------------------------------------------------------------
// Local CV+RRR parameters (bound by host when USE_LOCAL_REVAL=1)
// ---------------------------------------------------------------------------
#if USE_LOCAL_REVAL
cbuffer LocalRevalCB
{
    float gLocalRevalContribThreshold;
    float gLocalRevalPMin;
};
#endif

// ---------------------------------------------------------------------------
// Local CV+RRR estimator — uses reservoir-local information only.
//
// mu = clamp(neighborTargetPdf / pHatNoVis, 0, 1)
// The neighbor's targetPdf was computed WITH visibility in a prior pass,
// while pHatNoVis is the same target function WITHOUT visibility.
// Their ratio approximates the visibility at the neighbor's evaluation.
//
// Then standard CV+RRR: E[mu + (V - mu) / p] = E[V], unbiased.
// ---------------------------------------------------------------------------
float evalLocalRevalidation(float3 P, float3 Q, float3 bsdf, float3 Lo,
                             float G, float neighborTargetPdf, float pHatNoVis,
                             float contribThreshold, float pMin,
                             inout SampleGenerator sg)
{
    // Reservoir-local visibility estimate
    static const float kLumEps = 1e-7f;
    float mu = (pHatNoVis > kLumEps) ? clamp(neighborTargetPdf / pHatNoVis, 0.0f, 1.0f)
                                     : 0.5f;  // no data -> uncertain

    // Contribution-weighted residual bound (same as VisCache path)
    float3 C   = bsdf * Lo * G;
    float  res = luminance(C) * max(mu, 1.0f - mu);
    float  p   = clamp(res / contribThreshold, pMin, 1.0f);

    if (sampleNext1D(sg) < p)
    {
        float V = traceShadowRay(P, Q);
        // Unbiased CV+RRR estimator
        return mu + (V - mu) / p;
    }
    return mu;  // no trace — use reservoir-local estimate
}

// ---------------------------------------------------------------------------
// Visibility evaluation — three paths:
//   USE_VISCACHE_REVAL: CV+RRR via VisCache hash table (S11.3)
//   USE_LOCAL_REVAL:    CV+RRR via reservoir-local mu (no hash table)
//   Neither:            Vanilla — unconditional shadow ray
// ---------------------------------------------------------------------------
float evaluateVisibility(float3 P, float3 Q, float3 bsdf, float3 Lo,
                          float G, float neighborTargetPdf, float pHatNoVis,
                          float3 camPos, inout SampleGenerator sg)
{
#if USE_VISCACHE_REVAL
    // VisCache hash table CV+RRR (S11.3) — camPos now in VisCacheParams cbuffer.
    return evalRevalidationCV(P, Q, bsdf, Lo, G, sg);
#elif USE_LOCAL_REVAL
    // Reservoir-local CV+RRR (no hash table — ablation baseline)
    return evalLocalRevalidation(P, Q, bsdf, Lo, G, neighborTargetPdf, pHatNoVis,
                                  gLocalRevalContribThreshold, gLocalRevalPMin, sg);
#else
    // Vanilla: unconditional shadow ray for each neighbor
    return traceShadowRay(P, Q);
#endif
}
