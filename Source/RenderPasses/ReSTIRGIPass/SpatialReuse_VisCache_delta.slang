/***************************************************************************
 * SpatialReuse.cs.slang  (patched delta for ReSTIRGIPass)
 *
 * Apply this diff on top of DQLin/ReSTIR_PT's SpatialReuse.cs.slang.
 * Replaces the unconditional V(P,Q) shadow rays in the spatial reuse
 * loop with CV+RRR gated calls, reducing traces from k=5 to ~0.5–1.0
 * rays/pixel at steady state (§11.3 / §12).
 *
 * Integration theory (§12):
 *   - For each neighbor Q, compute C = BSDF(P) * Lo(Q) * G(P,Q)
 *   - Residual bound: res = luminance(C) * max(mu, 1-mu)
 *   - RR probability: p = clamp(res / contribThreshold, pMin, 1.0)
 *   - If trace: V_est = mu + (V - mu) / p  [unbiased]
 *   - If skip:  V_est = mu                 [no trace]
 *
 * Path-sharing amortization (why this works for GI):
 *   50–100 pixels sharing the same reused path map to ~3–5 L0 cells,
 *   warming the cache within-frame. Finest-level-only breaks this —
 *   see §15 ablation, multilevel vs. finest comparison.
 ***************************************************************************/

// Paste this block at the top of SpatialReuse.cs.slang, after existing imports:
#import "../VisCache/VisCache"
#import "../VisCache/ShadingCV"

// ---------------------------------------------------------------------------
// REPLACE the existing spatial reuse loop body with this version.
// The outer loop structure (neighbor selection, reservoir merge) is unchanged.
// Only the visibility evaluation changes.
//
// ORIGINAL (DQLin/ReSTIR_PT):
//   float V = TraceVisibilityRay(P, neighbor.secondaryHit.posW);
//   float contrib = EvalContrib(P, neighbor) * V;
//   UpdateReservoir(reservoir, neighbor, contrib);
//
// PATCHED (VisCache):
// ---------------------------------------------------------------------------

/*
for (int i = 0; i < gNumSpatialNeighbors; i++)
{
    PathReservoir neighbor = LoadNeighborReservoir(i);
    if (!neighbor.isValid()) continue;

    float3 Q  = neighbor.secondaryHit.posW;
    float3 Lo = neighbor.Lo;

    // Geometry term at the reconnection vertex
    float3 toQ = Q - P;
    float  distPQ = length(toQ);
    float3 dirPQ  = toQ / distPQ;
    float  G      = abs(dot(sd.N, dirPQ)) * abs(dot(neighbor.secondaryHit.N, -dirPQ))
                  / (distPQ * distPQ + 1e-6f);

    float3 bsdf   = EvalBSDF(sd, dirPQ);
    float3 C      = bsdf * Lo * G;

    // CV+RRR revalidation (replaces unconditional TraceVisibilityRay)
    float Vest    = evalRevalidationCV(P, Q, bsdf, Lo, G, gCamPos, sg);

    float contrib = luminance(C * Vest) * neighbor.invPDF;
    UpdateReservoir(reservoir, neighbor, contrib, sg);
}
*/

// ---------------------------------------------------------------------------
// execute() patch: retrieve VisCache buffers from InternalDictionary
// Add at the top of ReSTIRGIPass::execute() before the spatial reuse dispatch:
// ---------------------------------------------------------------------------

/*
void ReSTIRGIPass::retrieveVisCacheBuffers(const RenderData& rd)
{
    const auto& dict = rd.getDictionary();

    if (mVisCacheParams.enabled &&
        dict.keyExists("visCacheTable") && dict.keyExists("visCacheCapacity"))
    {
        mpVisCacheTable  = dict["visCacheTable"].get<ref<Buffer>>();
        mVisCacheCapacity = dict["visCacheCapacity"].get<uint32_t>();
    }
    else
    {
        mpVisCacheTable   = nullptr;
        mVisCacheCapacity = 0u;
        if (mVisCacheParams.enabled)
            logWarning("ReSTIRGIPass: VisCache buffers not found in dictionary. "
                       "Ensure VisCache pass runs before ReSTIRGIPass.");
    }

    // Upload to shader
    auto vars = mpSpatialReusePass->getRootVar();
    vars["gVHFTable"]          = mpVisCacheTable;
    vars["gTableCapacity"]     = mVisCacheCapacity;
    vars["gVarThreshold"]      = mVisCacheParams.pMin;  // re-use VisCache threshold
    vars["gPMin"]              = mVisCacheParams.pMin;
    vars["gFireflyBudget"]     = mVisCacheParams.contribThreshold;
}
*/
