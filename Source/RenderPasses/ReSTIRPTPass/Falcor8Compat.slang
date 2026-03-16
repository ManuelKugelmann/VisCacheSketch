/***************************************************************************
 # Falcor 4.x -> 8.0 porting shims for ReSTIR PT Pass.
 #
 # These free functions wrap Falcor 8's IMaterialInstance interface to
 # provide call-compatible replacements for the Falcor 4.x BSDF helpers
 # that DQLin's ReSTIR PT code relied on.  Keeping shims in one place
 # minimises the diff in PathTracer.slang and Shift.slang.
 **************************************************************************/

import Scene.Shading;
import Scene.Material.TextureSampler;       // ExplicitLodTextureSampler
import Scene.Material.MaterialFactory;      // MaterialSystem.getMaterialInstance()
import Rendering.Materials.IMaterialInstance;
import Utils.Sampling.SampleGenerator;
import Scene.Camera.Camera;                 // Camera, CameraData
import Utils.Math.Ray;                      // Ray

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
    BSDFSample bs = {};
    bool valid = mi.sample(sd, sg, bs, useImportanceSampling);
    if (valid)
    {
        result.wi        = bs.wo;
        result.pdf       = bs.pdf;
        result.weight    = bs.weight;
        result.lobe      = bs.lobeType;

        // Compute pdfSingle: the PDF contribution from only the sampled lobe class.
        // In DQLin's Falcor 4.4, bsdf.sample() returned this as a separate output
        // (the per-lobe selection-weighted PDF before adding cross-lobe MIS terms).
        // Falcor 8's mi.sample() only returns the combined PDF. We approximate
        // pdfSingle by re-evaluating with setActiveLobes, which is consistent with
        // how evalPdfBSDF computes filtered PDFs in shift mapping.
        bool isSampledSpecular = (bs.lobeType & ((uint)LobeType::Specular | (uint)LobeType::Delta)) != 0;
        // Specular class: 0x66 = Specular|Delta (reflection+transmission)
        // Diffuse class:  0x11 = Diffuse (reflection+transmission)
        uint sampledClassFlags = isSampledSpecular ? 0x66 : 0x11;
        ShadingData sdCopy = sd;
        sdCopy.mtl.setActiveLobes(sampledClassFlags);
        let miFiltered = _getMI(sdCopy);
        result.pdfSingle = miFiltered.evalPdf(sdCopy, bs.wo, useImportanceSampling);
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
    SampleGenerator sg = SampleGenerator(uint2(0), 0); // dummy – eval doesn't consume samples
    let mi = _getMI(sd);
    return mi.eval(sd, dir, sg);
}

float3 evalBSDFCosine(const ShadingData sd, float3 dir, uint allowedFlags)
{
    // Apply lobe mask via mtl.setActiveLobes before eval.
    ShadingData sdCopy = sd;
    if (allowedFlags != 0xffffffff && allowedFlags != 0xff)
        sdCopy.mtl.setActiveLobes(allowedFlags);
    SampleGenerator sg = SampleGenerator(uint2(0), 0);
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

float evalPdfBSDF(const ShadingData sd, float3 dir, uint allowedFlags)
{
    float pdfAll;
    return evalPdfBSDF(sd, dir, pdfAll, allowedFlags);
}

float evalPdfBSDF(const ShadingData sd, float3 dir, out float pdfAll, uint allowedFlags)
{
    // Full (all-lobe) PDF.
    let mi = _getMI(sd);
    pdfAll = mi.evalPdf(sd, dir, true);

    // Component PDF with lobe mask.
    // 0xff = LobeType::All, 0xffffffff = legacy "all" sentinel — both mean no filtering.
    if (allowedFlags != 0xffffffff && allowedFlags != 0xff)
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
    if (allowedFlags != 0xffffffff && allowedFlags != 0xff)
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

// ---------------------------------------------------------------------------
// computeRayPinholePrevFrame  --  Falcor 4.x camera helper
//
// Falcor 4 had Camera::computeRayPinholePrevFrame().  Falcor 8 removed it.
// We reconstruct the previous-frame ray using prevViewMat (rotation part)
// combined with current-frame intrinsics (cameraU/V/W lengths = FOV scaling,
// which don't change between frames).
// ---------------------------------------------------------------------------
extension Camera
{
    Ray computeRayPinholePrevFrame(uint2 pixel, uint2 frameDim, bool applyJitter = true)
    {
        // Previous-frame camera basis: extract orientation from prevViewMat
        // rows, scale by current-frame intrinsic lengths.
        float lenU = length(data.cameraU);
        float lenV = length(data.cameraV);
        float lenW = length(data.cameraW);

        // prevViewMat rows give right/up/forward in world space (transposed).
        float3 prevRight   = float3(data.prevViewMat[0][0], data.prevViewMat[0][1], data.prevViewMat[0][2]);
        float3 prevUp      = float3(data.prevViewMat[1][0], data.prevViewMat[1][1], data.prevViewMat[1][2]);
        float3 prevForward = float3(data.prevViewMat[2][0], data.prevViewMat[2][1], data.prevViewMat[2][2]);

        float3 prevCameraU = normalize(prevRight)   * lenU;
        float3 prevCameraV = normalize(prevUp)      * lenV;
        float3 prevCameraW = normalize(prevForward)  * lenW;

        // Compute sample position (same as computeRayPinhole).
        float2 p = (pixel + float2(0.5f, 0.5f)) / frameDim;
        if (applyJitter) p += float2(-data.jitterX, data.jitterY);
        float2 ndc = float2(2, -2) * p + float2(-1, 1);

        Ray ray;
        ray.origin = data.prevPosW;
        ray.dir = normalize(ndc.x * prevCameraU + ndc.y * prevCameraV + prevCameraW);

        float invCos = 1.f / dot(normalize(prevCameraW), ray.dir);
        ray.tMin = data.nearZ * invCos;
        ray.tMax = data.farZ * invCos;

        return ray;
    }
}
