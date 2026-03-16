/***************************************************************************
 # Falcor 4.x -> 8.0 porting shims for ReSTIR PT Pass.
 #
 # These free functions wrap Falcor 8's IMaterialInstance interface to
 # provide call-compatible replacements for the Falcor 4.x BSDF helpers
 # that DQLin's ReSTIR PT code relied on.  Keeping shims in one place
 # minimises the diff in PathTracer.slang and Shift.slang.
 **************************************************************************/

import Scene.Shading;
import Rendering.Materials.IMaterialInstance;
import Rendering.Materials.TexLODHelpers;
import Utils.Sampling.SampleGenerator;

// ---------------------------------------------------------------------------
// BSDFSample_ -- compatibility struct
// Falcor 4.x used `wi` for the sampled direction; Falcor 8 uses `wo`.
// ReSTIR PT also stores a per-component PDF (`pdfSingle`) used when
// kSeparatePathBSDF is enabled.
// ---------------------------------------------------------------------------
struct BSDFSample_
{
    float3 wi;          // Sampled direction (== BSDFSample::wo in Falcor 8).
    float  pdf;         // Combined PDF (all lobes).
    float  pdfSingle;   // Single-lobe PDF (used by kSeparatePathBSDF).
    float3 weight;      // BSDF * cosTheta / pdf.
    uint   lobe;        // Lobe type flags (same encoding as Falcor 8 LobeType).

    bool isLobe(LobeType type) { return (lobe & (uint)type) != 0; }
};

// ---------------------------------------------------------------------------
// Helper: obtain a material instance for a given ShadingData.
// ---------------------------------------------------------------------------
IMaterialInstance _getMI(const ShadingData sd)
{
    let lod = ExplicitLodTextureSampler(0.f);
    return gScene.materials.getMaterialInstance(sd, lod);
}

// ---------------------------------------------------------------------------
// sampleBSDF  --  Falcor 4.x: sampleBSDF(sd, sg, result, useImportanceSampling)
// ---------------------------------------------------------------------------
bool sampleBSDF(const ShadingData sd, inout SampleGenerator sg, out BSDFSample_ result, bool useImportanceSampling = true)
{
    result = {};
    let mi = _getMI(sd);
    BSDFSample bs;
    bool valid = mi.sample(sd, sg, bs, useImportanceSampling);
    if (valid)
    {
        result.wi        = bs.wo;
        result.pdf       = bs.pdf;
        result.pdfSingle = bs.pdf;   // Overwritten by caller when kSeparatePathBSDF.
        result.weight    = bs.weight;
        result.lobe      = bs.lobeType;
    }
    return valid;
}

// ---------------------------------------------------------------------------
// sampleBSDF_Reference  --  cosine-hemisphere sampling fallback
// ---------------------------------------------------------------------------
bool sampleBSDF_Reference(const ShadingData sd, inout SampleGenerator sg, out BSDFSample_ result)
{
    // Delegate to the material with importance sampling disabled (uniform cosine).
    return sampleBSDF(sd, sg, result, false);
}

// ---------------------------------------------------------------------------
// evalBSDFCosine  --  evaluate BSDF*cosTheta for a given direction
//
// Overloads mirror the original Falcor 4.x signatures:
//   evalBSDFCosine(sd, dir)
//   evalBSDFCosine(sd, dir, allowedFlags)
//   evalBSDFCosine(sd, dir, allowedFlags, isDelta)
// ---------------------------------------------------------------------------
float3 evalBSDFCosine(const ShadingData sd, float3 dir)
{
    SampleGenerator sg = SampleGenerator(0); // dummy – eval doesn't consume samples
    let mi = _getMI(sd);
    return mi.eval(sd, dir, sg);
}

float3 evalBSDFCosine(const ShadingData sd, float3 dir, uint allowedFlags)
{
    // Apply lobe mask via mtl.setActiveLobes before eval, then restore.
    ShadingData sdCopy = sd;
    if (allowedFlags != 0xffffffff)
        sdCopy.mtl.setActiveLobes(allowedFlags);
    SampleGenerator sg = SampleGenerator(0);
    let mi = _getMI(sdCopy);
    return mi.eval(sdCopy, dir, sg);
}

float3 evalBSDFCosine(const ShadingData sd, float3 dir, uint allowedFlags, bool isDelta)
{
    if (isDelta) return float3(0.f); // delta lobes have zero area measure
    return evalBSDFCosine(sd, dir, allowedFlags);
}

// ---------------------------------------------------------------------------
// evalPdfBSDF  --  evaluate PDF of BSDF sampling for a given direction
//
// Overloads:
//   evalPdfBSDF(sd, dir)                          -> combined PDF
//   evalPdfBSDF(sd, dir, out pdfAll, flags)        -> component + all PDF
//   evalPdfBSDF(sd, dir, out pdfAll, flags, isDelta) -> with delta guard
// ---------------------------------------------------------------------------
float evalPdfBSDF(const ShadingData sd, float3 dir)
{
    let mi = _getMI(sd);
    return mi.evalPdf(sd, dir, true);
}

float evalPdfBSDF(const ShadingData sd, float3 dir, out float pdfAll, uint allowedFlags)
{
    // Full (all-lobe) PDF.
    let mi = _getMI(sd);
    pdfAll = mi.evalPdf(sd, dir, true);

    // Component PDF with lobe mask.
    if (allowedFlags != 0xffffffff)
    {
        ShadingData sdCopy = sd;
        sdCopy.mtl.setActiveLobes(allowedFlags);
        let miFiltered = _getMI(sdCopy);
        float componentPdf = miFiltered.evalPdf(sdCopy, dir, true);
        return componentPdf;
    }
    return pdfAll;
}

float evalPdfBSDF(const ShadingData sd, float3 dir, out float pdfAll, uint allowedFlags, bool isDelta)
{
    if (isDelta) { pdfAll = 0.f; return 0.f; }
    return evalPdfBSDF(sd, dir, pdfAll, allowedFlags);
}

// ---------------------------------------------------------------------------
// evalPdfBSDFWithV  --  evaluate PDF using a different incident direction
//
// In the original DQLin code this re-evaluates the BSDF PDF at a vertex
// as if the path arrived from direction `-V` (the given view direction)
// rather than the one stored in ShadingData.
// ---------------------------------------------------------------------------
float evalPdfBSDFWithV(const ShadingData sd, float3 newV, float3 dir, uint allowedFlags)
{
    ShadingData sdCopy = sd;
    sdCopy.V = newV;
    if (allowedFlags != 0xffffffff)
        sdCopy.mtl.setActiveLobes(allowedFlags);
    let mi = _getMI(sdCopy);
    return mi.evalPdf(sdCopy, dir, true);
}

float evalPdfBSDFWithV(const ShadingData sd, float3 newV, float3 dir, uint allowedFlags, bool isDelta)
{
    if (isDelta) return 0.f;
    return evalPdfBSDFWithV(sd, newV, dir, allowedFlags);
}

// ---------------------------------------------------------------------------
// classifyAsRough / hasRoughComponent
//
// Falcor 4.x had these on ShadingData using sd.linearRoughness.
// Falcor 8 obtains roughness from BSDFProperties.
// ---------------------------------------------------------------------------

/// Returns true if the surface should be treated as "rough" (diffuse-like).
bool classifyAsRough(const ShadingData sd, float specularRoughnessThreshold)
{
    let mi = _getMI(sd);
    float roughness = mi.getProperties(sd).roughness;
    return roughness > specularRoughnessThreshold;
}

/// Returns true if the surface has any lobe whose roughness exceeds the threshold.
/// In the original DQLin code, hasRoughComponent(sd, 1.f) effectively checks
/// whether the material has any non-specular (diffuse) lobes.
bool hasRoughComponent(const ShadingData sd, float threshold)
{
    let mi = _getMI(sd);
    float roughness = mi.getProperties(sd).roughness;
    if (roughness > threshold) return true;
    // Also consider explicit diffuse lobes.
    uint lobes = mi.getLobeTypes(sd);
    if ((lobes & (uint)LobeType::Diffuse) != 0) return true;
    return false;
}

// ---------------------------------------------------------------------------
// getRoughness  --  convenience for callers that just need the scalar
// ---------------------------------------------------------------------------
float getRoughness(const ShadingData sd)
{
    let mi = _getMI(sd);
    return mi.getProperties(sd).roughness;
}

// ---------------------------------------------------------------------------
// getEmission  --  convenience to get emission from BSDFProperties
// ---------------------------------------------------------------------------
float3 getEmission(const ShadingData sd)
{
    let mi = _getMI(sd);
    return mi.getProperties(sd).emission;
}
