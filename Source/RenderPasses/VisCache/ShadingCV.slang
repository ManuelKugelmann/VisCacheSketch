/***************************************************************************
 * ShadingCV.slang
 *
 * CV+RRR shadow ray gating — high-level shading wrappers.
 * These build on vhfGate()/vhfCommit() from VisCache.slang.
 *
 * Provides:
 *   evalDirectLightingCV()     — drop-in for unconditional shadow ray
 *   vhfLightSelectionWeight()  — cached mu for ReSTIR DI target (§11.1)
 *   evalRevalidationCV()       — GI revalidation for spatial reuse (§12)
 *
 * Assumes caller provides:
 *   float traceShadowRay(float3 origin, float3 target);
 *   float3 evalBRDF(ShadingData sd, float3 L);
 ***************************************************************************/

#pragma once
#import "VisCache"

// ---------------------------------------------------------------------------
// Main entry point — replaces the unconditional shadow ray in direct lighting.
// C = BRDF * Le * G (always evaluated, never gated).
// ---------------------------------------------------------------------------
float3 evalDirectLightingCV(ShadingData sd,
                             float3      lightPos,
                             float3      Le,
                             float       G,
                             inout SampleGenerator sg)
{
    // Analytic lighting term — always computed (§4)
    float3 C = evalBRDF(sd, normalize(lightPos - sd.posW)) * Le * G;

    // Gate/commit via core API (firefly-aware via contribution luminance).
    VHFGateResult g = vhfGate(sd.posW, lightPos, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(sd.posW, lightPos);
        float w = vhfCommit(sd.posW, lightPos, V, g);
        return C * w;
    }
    return C * g.visWeight;
}

// ---------------------------------------------------------------------------
// Light selection variant (§11.1): replace V=1 with cached mu in
// the ReSTIR DI target function.
// Unbiased: mu_min > 0 guarantees every light has nonzero selection weight,
// preserving support coverage required for unbiased RIS.
// See: Boksansky & Meister 2025 for concurrent neural approach.
// ---------------------------------------------------------------------------
float vhfLightSelectionWeight(float3 posA, float3 posB)
{
    static const float kMuMin = 0.05f;  // epsilon-greedy floor, prevents feedback death

    VHFResult r = vhfLookup(posA, posB);
    float mu    = r.valid ? max(r.mu, kMuMin) : 1.0f;  // MISS -> assume visible

    // L0 visibility estimate suffices for candidate weighting (§11.1)
    return mu;
}

// ---------------------------------------------------------------------------
// GI revalidation variant (§12): contribution-weighted RR for
// V(P, Q) where Q is a neighbor's secondary hit.
// Called inside the spatial reuse loop in ReSTIRPTPass.
// Expected traces: ~0.5-1.0 per pixel at k=5 neighbors (vs. 5.0 unoptimised).
// ---------------------------------------------------------------------------
float evalRevalidationCV(float3 P, float3 Q,
                          float3 bsdf, float3 Lo, float G,
                          inout SampleGenerator sg)
{
    float3 C = bsdf * Lo * G;

    // Use gate/commit with contribution-aware firefly budget.
    VHFGateResult g = vhfGate(P, Q, sampleNext1D(sg), luminance(C));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(P, Q);
        return vhfCommit(P, Q, V, g);
    }

    // No cache + no trace: return 0.5 (uncertain) when gate says no trace.
    // This happens when the cache has a converged entry.
    return g.visWeight;
}
