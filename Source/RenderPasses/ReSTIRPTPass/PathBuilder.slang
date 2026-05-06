/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/
#include "Scene/SceneDefines.slangh"

// [Falcor 8] MaterialShading merged into Scene.Material.MaterialFactory (imported via Scene.Scene)
import LoadShadingData;
import Utils.Debug.PixelDebug;
import Utils.Math.HashUtils;
import Params;
import PathReservoir;
import Rendering.Utils.PixelStats;
import Scene.RaytracingInline;
// [Falcor 8] MaterialShading merged into Scene.Material.MaterialFactory (imported via Scene.Scene)
import Utils.Sampling.TinyUniformSampleGenerator;

#if BPR
static const int kRcWiCount = 2;
#else
static const int kRcWiCount = 1;
#endif

/// Builds a Path and a PathPrefix.
struct PathBuilder
{
    TriMeshHitInfo rcVertexHit;
    float3 rcVertexWi[kRcWiCount];
    uint cachedRandomSeed;
    TinyUniformSampleGenerator sg;
    int rcVertexLength = kMaximumPathLength;
    ReSTIRPathFlags pathFlags;
    float3 cachedJacobian = 1.f;

    [mutating]
    void init<S : ISampleGenerator>(inout S sg)
    {
        this.sg = TinyUniformSampleGenerator(jenkinsHash(sg.next()));
        rcVertexWi[0] = float3(0.f);
        rcVertexHit.instanceID = 0xffffffff;
#if BPR
        rcVertexWi[1] = float3(0.f);
#endif
    }

    void finalize(inout PathReservoir pathReservoir)
    {
#if BPR
        pathReservoir.weight = PathReservoir::toScalar(pathReservoir.F);

        // when kNEESamples == 1, we can use cachedJacobian slot to store NEE contribution so that we don't need to recompute in reuse
        if (any(pathReservoir.rcVertexIrradiance[1] > 0.f)) pathReservoir.F -= pathReservoir.cachedJacobian;
        else pathReservoir.cachedJacobian = 0.f;
#endif
        pathReservoir.M = 1;
    }

    [mutating]
    bool addEscapeVertex(RestirPathTracerParams params, uint pathLength, float3 wi, float3 pathWeight, float3 postfixWeight, bool useHybridShift,
        float russianroulettePDF, float misWeight, float lightPdf, int lightType, inout PathReservoir pathReservoir, bool forceAdd = false)
    {
        bool selected = false;

        if (pathLength >= 1)
        {
            bool is_rcVertex = pathLength == rcVertexLength;

#if BPR
            pathReservoir.F += pathWeight;

            if (is_rcVertex)
            {
                pathReservoir.rcVertexBSDFLightSamplingIrradiance = postfixWeight / misWeight;
                pathReservoir.lightPdf = lightPdf;
                pathReservoir.rcVertexWi[0] = wi;
            }
            else
            {
                pathReservoir.rcVertexWi[0] = rcVertexWi[0];
                pathReservoir.rcVertexIrradiance[0] = postfixWeight;
            }
            pathReservoir.rcVertexHit = rcVertexHit;

            pathReservoir.pathFlags = pathFlags;
            pathReservoir.pathFlags.insertPathLength(pathLength); // excluding the NEE vertex
            pathReservoir.pathFlags.insertRcVertexLength(rcVertexLength);
#else
            if (forceAdd || pathReservoir.add(pathWeight, russianroulettePDF, sg))
            {
                selected = true;
                pathReservoir.pathFlags = pathFlags;
                pathReservoir.pathFlags.insertPathLength(pathLength);
                pathReservoir.pathFlags.insertRcVertexLength(rcVertexLength);
                pathReservoir.pathFlags.insertLastVertexNEE(false);
                pathReservoir.rcVertexIrradiance[0] = postfixWeight;
                pathReservoir.F = pathWeight;
                pathReservoir.rcVertexWi[0] = rcVertexWi[0];
                pathReservoir.rcVertexHit = rcVertexHit;

                pathReservoir.cachedJacobian = cachedJacobian;

                pathReservoir.rcRandomSeed = cachedRandomSeed;

                if (is_rcVertex) // at rcVertex
                {
                    pathReservoir.rcVertexWi[0] = wi;
                    pathReservoir.rcVertexIrradiance[0] /= misWeight; // exclude last vertex dependent mis weight
                }
                pathReservoir.lightPdf = lightPdf;
                pathReservoir.pathFlags.insertLightType(lightType);
            }
#endif
        }

        return selected;
    }

    [mutating]
    bool addNeeVertex(RestirPathTracerParams params, uint pathLength, float3 wi, float3 pathWeight, float3 postfixWeight, bool useHybridShift,
        float russianroulettePDF, float misWeight, float lightPdf, int lightType, inout PathReservoir pathReservoir, bool forceAdd = false,
        HitInfo neeLightHit = HitInfo(),
        float3 lightLeOnlyContribution = float3(0.f),
        float3 cachedJacobianForceNEE = float3(0.f))
    {
        bool selected = false;

        if (pathLength >= 1)
        {
            bool is_rcVertex = pathLength == rcVertexLength;
            // Lin 2026 §6.2.3 forced NEE light reconnection: when the source path
            // has no earlier rcVertex selected (rcVertexLength still at the
            // sentinel kMaximumPathLength), the NEE light vertex itself becomes
            // the rcVertex. Phase 1.B.1 scope: Emissive lights only.
            //
            // *** DISABLED 2026-05-06 *** — three iterations of structurally
            // correct fixes (dstF2=1 in Shift.slang gated on isForcedNEE, Le-only
            // rcVertexIrradiance override, cachedJacobian populated with
            // scatterPdf+G_src) plateau at Cornell mean_err 16.78% vs canonical
            // 3.87% (4× gap). Diagnosis: Shift.slang's MIS weight at line ~569
            // uses `dstRcVertexScatterPdfAll = evalPdfBSDF(rcVertexSd, ...)` at
            // the LIGHT surface (returns 0 for emissives) → MIS degenerates to
            // 1.0 → no proper bias correction against the BSDF-sample alternative
            // strategy that also fires for d=2 in unified-DI/GI mode. Multiple
            // shift-code MIS bookkeeping points need re-derivation against
            // Lin 2026 supplemental §5 before re-enable. See:
            //   .plans/restirpt-forced-nee-reconnection.md
            //   PORT_NOTES.md "Future additions"
            // The plumbing (LightSample.packedHit, lightNormalW, addNeeVertex
            // params, isForcedNEE flag, gated dstF2=1 in Shift) stays as
            // scaffolding for the next attempt — flip this gate to re-enable.
            bool force_nee_as_rcVertex = false;
            // Original gate (re-enable when shift MIS is corrected):
            //bool force_nee_as_rcVertex = (rcVertexLength == kMaximumPathLength) && useHybridShift && neeLightHit.isValid();
            bool effective_is_rcVertex = is_rcVertex || force_nee_as_rcVertex;
            uint effective_rcVertexLength = force_nee_as_rcVertex ? pathLength : rcVertexLength;

#if BPR
            pathReservoir.F += pathWeight;

            if (effective_is_rcVertex)
            {
                pathReservoir.cachedJacobian = pathWeight;
                pathReservoir.rcVertexIrradiance[1] = postfixWeight * lightPdf / misWeight;
                pathReservoir.insertRcLightType(lightType);
                pathReservoir.rcLightPdf = lightPdf;
                pathReservoir.rcVertexWi[1] = wi;

            }
            else
            {
                pathReservoir.rcVertexWi[0] = rcVertexWi[0];
                pathReservoir.rcVertexIrradiance[0] = postfixWeight;
            }
            pathReservoir.rcVertexHit = rcVertexHit;

            pathReservoir.pathFlags = pathFlags;
            pathReservoir.pathFlags.insertPathLength(pathLength); // excluding the NEE vertex
            pathReservoir.pathFlags.insertRcVertexLength(effective_rcVertexLength);

            selected = true;
#else
            if (forceAdd || pathReservoir.add(pathWeight, russianroulettePDF, sg))
            {
                selected = true;
                pathReservoir.pathFlags = pathFlags;
                pathReservoir.pathFlags.insertPathLength(pathLength); // excluding the NEE vertex
                pathReservoir.pathFlags.insertRcVertexLength(effective_rcVertexLength);
                pathReservoir.pathFlags.insertLastVertexNEE(true);
                pathReservoir.rcVertexIrradiance[0] = postfixWeight;
                pathReservoir.F = pathWeight;
                pathReservoir.rcVertexWi[0] = rcVertexWi[0];
                pathReservoir.rcVertexHit = rcVertexHit;
                if (force_nee_as_rcVertex)
                {
                    // Lin 2026 §6.2.3: override with the NEE light surface hit
                    // (Emissive triangle synthesized in generateEmissiveSample).
                    pathReservoir.rcVertexHit.initFromHitInfo(neeLightHit);
                    pathReservoir.pathFlags.insertIsForcedNEE(true);
                }

                pathReservoir.cachedJacobian = cachedJacobian;
                if (force_nee_as_rcVertex)
                {
                    // PathBuilder.cachedJacobian is uninitialized when no prior
                    // rcVertex was selected (the force-NEE precondition). Override
                    // with caller-computed (scatterPdf_at_primary, 0, G_src) so the
                    // existing Shift.slang Jacobian computation
                    //   J = (G_dst / G_src) × (BSDFPdf_dst / BSDFPdf_src)
                    // has valid source-side values. y-component unused.
                    pathReservoir.cachedJacobian = cachedJacobianForceNEE;
                }

                pathReservoir.rcRandomSeed = cachedRandomSeed;

                if (effective_is_rcVertex) // at rcVertex (or forced NEE per §6.2.3)
                {
                    if (force_nee_as_rcVertex)
                    {
                        // Force-NEE-as-light: rcVertex IS the light. The shift's dstF1
                        // contributes BSDF×cos at destination's primary; we must NOT
                        // include source's BSDF×cos in rcVertexIrradiance (it'd
                        // double-count). Override with Le×thp×lightPdf/misWeight so
                        // the existing shift formula `dstF2/dstPDF2 × rcVertexIrradiance`
                        // (with dstF2=1 from Shift.slang's isRcVertexNEE branch and
                        // dstPDF2=lightPdf) yields Le×thp/misWeight.
                        pathReservoir.rcVertexIrradiance[0] = lightLeOnlyContribution * lightPdf / misWeight;
                    }
                    else
                    {
                        pathReservoir.rcVertexIrradiance[0] = pathReservoir.rcVertexIrradiance[0] * lightPdf / misWeight;
                    }
                    pathReservoir.rcVertexWi[0] = wi;
                }
                pathReservoir.lightPdf = lightPdf;
                pathReservoir.pathFlags.insertLightType(lightType);
            }
#endif
        }

        return selected;
    }

    [mutating] void markEscapeVertexAsRcVertex(RestirPathTracerParams params, uint pathLength, inout PathReservoir pathReservoir, HitInfo hit, bool isDelta,
        bool isTransmission, bool isSpecularBounce, float lightPdf, uint lightType, float3 rcVertexIrradiance, float3 rcVertexWi, float prevScatterPdf, float geometryFactor)
    {
        pathReservoir.pathFlags.insertRcVertexLength(pathLength);

        pathReservoir.rcVertexHit.initFromHitInfo(hit);
        pathReservoir.pathFlags.insertIsDeltaEvent(isDelta, true);
        pathReservoir.pathFlags.insertIsTransmissionEvent(isTransmission, true);
        pathReservoir.pathFlags.insertIsSpecularBounce(isSpecularBounce, true);
        pathReservoir.lightPdf = lightPdf;
        pathReservoir.cachedJacobian.x = prevScatterPdf;
        pathReservoir.pathFlags.insertLightType(lightType);
        pathReservoir.rcVertexIrradiance[0] = rcVertexIrradiance;
        pathReservoir.rcVertexWi[0] = rcVertexWi;
        pathReservoir.cachedJacobian.z = geometryFactor;
    }
};

