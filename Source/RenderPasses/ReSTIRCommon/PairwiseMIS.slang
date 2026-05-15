/***************************************************************************
 * PairwiseMIS.slang
 *
 * RTXDI-faithful pairwise MIS bias correction for reservoir resampling.
 * Generic across DI / NEE / PT — captures the canonical "snapshot, re-init,
 * stream neighbours with m_j, accumulate m_canon, re-stream canonical at
 * finalize" pattern as a single struct with methods.
 *
 * Reference: RTXDI SDK ResamplingFunctions.hlsli
 *   - RTXDI_StreamNeighborWithPairwiseMIS (line 250)
 *   - RTXDI_StreamCanonicalWithPairwiseStep (line 292)
 *   - RTXDI_PairwiseMisWeight + RTXDI_MFactor (RtxdiMath.hlsli line 104+)
 * Reference: Boksansky et al. 2022 "Rearchitecting Spatiotemporal
 *   Resampling for Production" §4.
 *
 * Math (same-surface fallback + RTXDI-faithful path):
 *   m_j     = (nbr.targetPdf × Mcn) / (pHat_reader(y_nbr) × M_canon + nbr.targetPdf × Mcn)
 *   m_canon = (cWAtC × M_canon) / (cWAtN × Mcn + cWAtC × M_canon)
 *     where cWAtC = canon's pHat at canon's surface (= canon.targetPdf, stored)
 *     and   cWAtN = canon's pHat at nbr's surface (needs neighbour ShadingData)
 *     Same-surface fallback (cWAtN = cWAtC) collapses to M_canon / (M_canon + Mcn).
 *   wn      = m_j × pHat_reader × nbr.W × Mcn        // RIS weight for streaming
 *   M_eff  += m_j × Mcn                              // m-weighted M for finalize
 *
 * After streaming all N neighbours, re-stream canonical with:
 *   wn_canon = canonMISAcc × canon.wSum_snapshot
 *   M_eff   += canonMISAcc × M_canon_snapshot
 *
 * Finalize: W = local.wSum / (pHat_winner × M_eff). The m-weighted M is the
 * load-bearing step — without it the equal-pHat-equal-M case gives W/2.
 *
 * Why generic: DI's spatial-pixel / temporal / cell merges; NEE's per-vertex
 * spatial/temporal merges (when added); PT's path-reservoir merges (with
 * extra Jacobian term in pHat eval). The accumulator state is identical
 * across these; only the per-pass "compute pHat at surface for stored
 * sample" function differs.
 ***************************************************************************/

#pragma once

import RenderPasses.ReSTIRCommon.Reservoir;

// Generic pairwise MIS accumulator. Holds the snapshotted canonical state
// + per-iteration accumulators. Used in three phases:
//   1. snapshot()      — capture canonical state before merge loop, re-init local
//   2. addNeighbourMIS() — for each neighbour, compute m_j and accumulate m_canon
//   3. finalize()      — re-stream canonical, overwrite local.M with M_eff
struct PairwiseMisState
{
    float canonM;           ///< M of canonical at snapshot time.
    float canonWSum;        ///< wSum of canonical at snapshot time.
    float canonTargetPdf;   ///< Stored targetPdf of canonical (= cWAtC).
    uint  canonLightTypeIndex;
    uint  canonPayload;
    float canonMISAcc;      ///< Σ m_canon_j across neighbours.
    float MEff;             ///< Σ (m_j × Mcn) — m-weighted M accumulator.
    bool  anyNeighbourStreamed;

    static PairwiseMisState empty()
    {
        PairwiseMisState s;
        s.canonM = 0.f; s.canonWSum = 0.f; s.canonTargetPdf = 0.f;
        s.canonLightTypeIndex = 0u; s.canonPayload = 0u;
        s.canonMISAcc = 0.f; s.MEff = 0.f; s.anyNeighbourStreamed = false;
        return s;
    }

    // Compute m_j given the four pHat values and M values.
    //   nWAtN = nbr's pHat at nbr's surface (= nbr.targetPdf, stored)
    //   nWAtC = nbr's pHat at canon's surface (= pHat_reader, computed)
    //   Mcn   = neighbour's M (capped, e.g. min(nbr.M, gMCap))
    // m_j is the Talbot pairwise weight for streaming the neighbour:
    //   m_j = nWAtN × Mcn / (nWAtC × M_canon + nWAtN × Mcn)
    static float computeMJ(float nWAtN, float nWAtC, float Mcn, float MCanon)
    {
        float denom = nWAtC * MCanon + nWAtN * Mcn;
        return (denom > 0.f) ? (nWAtN * Mcn / denom) : 0.f;
    }

    // Compute m_canon contribution from one neighbour. If cWAtN > 0, uses
    // RTXDI-faithful formula; otherwise falls back to M-ratio same-surface
    // approximation. cWAtN_provided=false means "neighbour surface eval
    // failed or unavailable, use M-ratio fallback".
    static float computeMCanon(float cWAtN, float cWAtC, float Mcn, float MCanon, bool cWAtN_provided)
    {
        if (!cWAtN_provided)
        {
            // M-ratio same-surface approximation.
            float Msum = MCanon + Mcn;
            return (Msum > 0.f) ? (MCanon / Msum) : 0.f;
        }
        float denom = cWAtN * Mcn + cWAtC * MCanon;
        return (denom > 0.f) ? (cWAtC * MCanon / denom) : 0.f;
    }
};
