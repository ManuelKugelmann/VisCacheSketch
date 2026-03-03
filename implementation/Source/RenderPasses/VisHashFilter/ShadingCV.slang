/***************************************************************************
 * ShadingCV.slang
 *
 * CV+RRR shadow ray gating for the PathTracer shading pass.
 * Drop-in replacement for unconditional traceShadowRay() calls.
 *
 * USAGE in PathTracer.slang (or ShadingPass.cs.slang):
 *
 *   #import "VisHashFilter"
 *   #import "ShadingCV"
 *
 *   // Replace:
 *   //   float V = traceShadowRay(sd.posW, lightPos);
 *   //   return C * V;
 *   // With:
 *   //   return evalDirectLightingCV(sd, lightPos, Le, G, sg);
 *
 * Unbiased: E[mu + (V - mu) / p] = E[V] for any cache quality.
 * Self-regulating: low var → low p → few traces → cache updates → var drops.
 ***************************************************************************/

#pragma once
#import "VisHashFilter"

// Assumed to be provided by the host PathTracer:
//   float traceShadowRay(float3 origin, float3 target);
//   float3 evalBRDF(ShadingData sd, float3 L);
//   cbuffer Camera { float3 gCamPos; }

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

    // Cache lookup
    VHFResult r = vhfLookup(sd.posW, lightPos, gCamPos);

    if (!r.valid)
    {
        // Cold MISS — unconditional trace, insert, baseline cost
        float V = traceShadowRay(sd.posW, lightPos);
        vhfInsert(sd.posW, lightPos, V, gCamPos);
        return C * V;
    }

    // ---------------------------------------------------------------
    // Adaptive pMin — scale floor by contribution to suppress fireflies
    // at penumbra edges where p is forced low (§10.1).
    // ---------------------------------------------------------------
    float contrib  = luminance(C) * max(r.mu, 1.0f - r.mu);
    float pFloor   = clamp(contrib / gFireflyBudget, gPMin, 1.0f);
    float p        = clamp(r.var / gVarThreshold, pFloor, 1.0f);

    if (sampleUniform1D(sg) < p)
    {
        // Trace correction ray
        float V = traceShadowRay(sd.posW, lightPos);
        vhfInsert(sd.posW, lightPos, V, gCamPos);
        // Unbiased CV+RRR estimator
        return C * (r.mu + (V - r.mu) / p);
    }

    // No trace — use cached mean
    return C * r.mu;
}

// ---------------------------------------------------------------------------
// Light selection variant (§11.1): replace V=1 with cached mu in
// the ReSTIR DI target function.
// Unbiased: mu_min > 0 guarantees every light has nonzero selection weight,
// preserving support coverage required for unbiased RIS.
// See: Bokšanský & Meister 2025 for concurrent neural approach.
// ---------------------------------------------------------------------------
float vhfLightSelectionWeight(float3 shadingPos, float3 lightPos,
                               float3 Le, float G, float3 camPos)
{
    static const float kMuMin = 0.05f;  // epsilon-greedy floor, prevents feedback death

    VHFResult r = vhfLookup(shadingPos, lightPos, camPos);
    float mu    = r.valid ? max(r.mu, kMuMin) : 1.0f;  // MISS → assume visible

    // L0 visibility estimate suffices for candidate weighting (§11.1)
    return mu;
}

// ---------------------------------------------------------------------------
// GI revalidation variant (§12): contribution-weighted RR for
// V(P, Q) where Q is a neighbor's secondary hit.
// Called inside the spatial reuse loop in ReSTIRGIPass.
// Expected traces: ~0.5–1.0 per pixel at k=5 neighbors (vs. 5.0 unoptimised).
// ---------------------------------------------------------------------------
float evalRevalidationCV(float3 P, float3 Q,
                          float3 bsdf, float3 Lo, float G,
                          float3 camPos,
                          inout SampleGenerator sg)
{
    float3 C = bsdf * Lo * G;

    VHFResult r = vhfLookup(P, Q, camPos);
    float mu    = r.valid ? r.mu : 0.5f;  // no cache → assume 50% uncertain

    // Max possible residual for this neighbor (§12)
    float res = luminance(C) * max(mu, 1.0f - mu);
    float p   = clamp(res / gVarThreshold, gPMin, 1.0f);

    if (sampleUniform1D(sg) < p)
    {
        float V = traceShadowRay(P, Q);
        vhfInsert(P, Q, V, camPos);
        return mu + (V - mu) / p;
    }
    return mu;  // no trace
}
