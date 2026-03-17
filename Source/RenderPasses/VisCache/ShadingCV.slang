/***************************************************************************
 * ShadingCV.slang
 *
 * High-level shading wrappers built on the core vhfGate()/vhfCommit() API
 * from VisCache.slang. These provide drop-in replacements for unconditional
 * shadow ray tracing in various rendering contexts.
 *
 * Three entry points for three use cases:
 *
 *   evalDirectLightingCV() — Direct lighting (NEE)
 *     Replaces the unconditional shadow ray in next event estimation.
 *     The BRDF * Le * G contribution is always computed (it's cheap);
 *     only the shadow ray is gated by the cache. Returns the weighted
 *     contribution C * visWeight.
 *
 *   vhfLightSelectionWeight() — Light selection bias (§11.1)
 *     Returns cached visibility mu for a light, used to bias ReSTIR DI
 *     light candidate selection toward likely-visible lights. An epsilon
 *     floor (kMuMin) prevents any light from being completely excluded,
 *     which is required for unbiased RIS (all candidates must have
 *     nonzero selection probability).
 *
 *   evalRevalidationCV() — GI revalidation (§12)
 *     Used in spatial reuse to evaluate V(P, Q) where Q is a neighbor's
 *     secondary hit. Contribution-aware: high-contribution revalidation
 *     edges get higher trace probability. Expected to reduce reconnection
 *     shadow rays from ~5.0 per pixel (k=5 neighbors) to ~0.5-1.0.
 *
 * All functions are unbiased: E[output] = E[ground truth].
 *
 * Assumes the importing file provides:
 *   float traceShadowRay(float3 origin, float3 target);
 *   float3 evalBRDF(ShadingData sd, float3 L);
 ***************************************************************************/

#pragma once

#if USE_VISCACHE

import VisCache;
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif

// ===========================================================================
// DIRECT LIGHTING WITH CV+RRR (drop-in shadow ray replacement)
// ===========================================================================

// ---------------------------------------------------------------------------
// evalDirectLightingCV: replaces the unconditional shadow ray in direct
// lighting (next event estimation).
//
// Pipeline:
//   1. Compute analytic lighting C = BRDF * Le * G (always, never gated)
//   2. Query cache: should we trace the shadow ray?
//   3a. If yes: trace, insert result, compute CV+RRR weight w
//   3b. If no:  use cached mu as weight w
//   4. Return C * w
//
// Why C is always computed: the BRDF and geometry terms are cheap (no ray
// trace), and computing them unconditionally simplifies the estimator.
// The expensive part (shadow ray) is what we gate.
//
// The contribLuminance parameter (= luminance(C)) enables firefly-aware
// adaptive pMin: bright contributions get higher trace probability to
// prevent weight explosion.
// ---------------------------------------------------------------------------
float3 evalDirectLightingCV(ShadingData sd,
                             float3      lightPos,
                             float3      Le,
                             float       G,
                             inout SampleGenerator sg)
{
    // Analytic lighting term — always computed, never gated.
    float3 C = evalBRDF(sd, normalize(lightPos - sd.posW)) * Le * G;

    // Gate/commit via core API. Uses stochastic xi from the sample generator
    // (appropriate for per-pixel NEE where temporal stability isn't critical).
    // Contribution luminance enables firefly-aware adaptive pMin.
    VHFGateResult g = vhfGate(sd.posW, lightPos, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(sd.posW, lightPos);
        float w = vhfCommit(sd.posW, lightPos, V, g);
        return C * w;  // CV+RRR weighted contribution
    }
    return C * g.visWeight;  // Cached mean — no shadow ray needed
}

// ===========================================================================
// LIGHT SELECTION WEIGHT (§11.1)
// ===========================================================================

// ---------------------------------------------------------------------------
// vhfLightSelectionWeight: returns a visibility-biased weight for light
// candidate selection in ReSTIR DI.
//
// Standard ReSTIR DI samples lights proportional to their unoccluded
// contribution (assuming V=1). This wastes samples on fully occluded lights.
// By multiplying the selection weight by cached mu, lights that are likely
// occluded get proportionally fewer samples.
//
// kMuMin is the epsilon-greedy floor: even lights with mu=0 (fully occluded)
// get a minimum selection weight of kMuMin. This is REQUIRED for unbiased
// RIS — every light must have nonzero selection probability, otherwise the
// support coverage condition is violated and the estimator becomes biased.
//
// On cold miss (no cache entry): returns 1.0 (assume visible). This is
// conservative — new lights are always considered until the cache learns
// their visibility. This prevents feedback death where an unseen light
// never gets selected and therefore never gets cached.
//
// posB: world-space light position for finite lights, or
//       vhfEncodeDirection(dir) for env map / directional lights.
//
// See: Boksansky & Meister 2025 for a concurrent neural approach to the
// same problem.
// ---------------------------------------------------------------------------
float vhfLightSelectionWeight(float3 posA, float3 posB)
{
    static const float kMuMin = 0.05f;  // Epsilon-greedy floor (prevents feedback death)

    VHFResult r = vhfLookup(posA, posB);
    // MISS → assume visible (1.0): conservative, prevents feedback death.
    // HIT  → clamp to [kMuMin, 1.0]: bias toward visible lights, but never
    //         completely exclude any light (unbiased RIS requirement).
    float mu = r.valid ? max(r.mu, kMuMin) : 1.0f;

    return mu;
}

// ===========================================================================
// GI REVALIDATION (§12)
// ===========================================================================

// ---------------------------------------------------------------------------
// evalRevalidationCV: evaluate visibility V(P, Q) for spatial reuse
// revalidation in ReSTIR PT / GI.
//
// Context: during spatial reuse, we merge a neighbor's path reservoir into
// our own. The neighbor's secondary hit Q may not be visible from our
// primary hit P. We need to evaluate V(P, Q) to revalidate the reservoir.
//
// Without VisCache: every spatial neighbor requires a shadow ray, so k=5
// neighbors means 5 shadow rays per pixel per spatial reuse round.
//
// With VisCache: most reconnection edges pass through well-converged cache
// entries (mu ≈ 0 or mu ≈ 1), so the RR probability is low and most rays
// are skipped. Expected cost: ~0.5-1.0 rays per pixel at k=5 neighbors.
//
// The contribution-aware firefly budget uses luminance(bsdf * Lo * G) to
// raise pMin for high-contribution paths, preventing weight explosion on
// bright caustic reconnections.
//
// Returns the CV+RRR visibility weight (unbiased estimate of V).
// ---------------------------------------------------------------------------
float evalRevalidationCV(float3 P, float3 Q,
                          float3 bsdf, float3 Lo, float G,
                          inout SampleGenerator sg)
{
    float3 C = bsdf * Lo * G;

    // Gate/commit with contribution-aware firefly budget.
    // Uses stochastic xi (appropriate since each reservoir merge is
    // statistically independent).
    VHFGateResult g = vhfGate(P, Q, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(P, Q);
        return vhfCommit(P, Q, V, g);
    }

    // Cache says "skip" — return cached mu as the visibility estimate.
    // This is the common path for well-converged entries.
    return g.visWeight;
}

// ===========================================================================
// Diagnostic overloads — write per-pixel heatmap data.
// Enable by adding VISCACHE_DIAGNOSTICS=1 to shader DefineList.
// ===========================================================================
#ifdef VISCACHE_DIAGNOSTICS

float3 evalDirectLightingCV(ShadingData sd,
                             float3      lightPos,
                             float3      Le,
                             float       G,
                             inout SampleGenerator sg,
                             uint2 pixel)
{
    float3 C = evalBRDF(sd, normalize(lightPos - sd.posW)) * Le * G;
    VHFGateResult g = vhfGate(sd.posW, lightPos, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(sd.posW, lightPos);
        float w = vhfCommit(sd.posW, lightPos, V, g);
        vcWriteDiag(pixel, g, true, V);
        return C * w;
    }
    vcWriteDiag(pixel, g, false, 0.f);
    return C * g.visWeight;
}

float evalRevalidationCV(float3 P, float3 Q,
                          float3 bsdf, float3 Lo, float G,
                          inout SampleGenerator sg,
                          uint2 pixel)
{
    float3 C = bsdf * Lo * G;
    VHFGateResult g = vhfGate(P, Q, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(P, Q);
        float w = vhfCommit(P, Q, V, g);
        vcWriteDiag(pixel, g, true, V);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f);
    return g.visWeight;
}

#endif // VISCACHE_DIAGNOSTICS

#endif // USE_VISCACHE
