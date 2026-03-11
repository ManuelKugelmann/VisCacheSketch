/***************************************************************************
 * FinalShading.cs.slang
 *
 * Final shading for ReSTIR DI — evaluates RTXDI-selected light samples.
 *
 * Three modes (compile-time defines):
 *   USE_VISCACHE=0:           Vanilla — unconditional shadow ray per sample.
 *   USE_VISCACHE=1, LIGHTSEL=0: CV+RRR shadow ray gating only (S11.3).
 *   USE_VISCACHE=1, LIGHTSEL=1: + cached mu in target function (S11.1).
 *
 * Unbiased in all modes: E[mu + (V - mu) / p] = E[V].
 ***************************************************************************/

import Scene.Scene;
import Scene.HitInfo;
import Scene.ShadingData;
import Scene.Material.MaterialSystem;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;
import Rendering.Materials.IBSDF;
import Rendering.RTXDI.RTXDI;
import Rendering.Lights.LightHelpers;

Texture2D<PackedHitInfo>  gVBuffer;
RWTexture2D<float4>       gColorOutput;

cbuffer PerFrameCB
{
    uint2 gFrameDim;
};

static const float kFireflyClamp    = 50.0f;
static const float kDistanceEps     = 1e-6f;
static const float kShadowRayOffset = 1e-4f;

// ---------------------------------------------------------------------------
// traceShadowRay — required by ShadingCV.slang's evalDirectLightingCV().
// ---------------------------------------------------------------------------
float traceShadowRay(float3 origin, float3 target)
{
    float3 dir  = target - origin;
    float  dist = length(dir);
    if (dist < kDistanceEps) return 1.0f;
    dir /= dist;

    Ray ray = Ray(origin, dir, kShadowRayOffset, dist - kShadowRayOffset);
    SceneRayQuery<0> rayQuery;
    return rayQuery.traceVisibilityRay(ray) ? 1.0f : 0.0f;
}

// Dummy evalBRDF satisfies Slang linker for ShadingCV.slang import.
// Only evalRevalidationCV() is called here (not evalDirectLightingCV()),
// so this stub is never invoked at runtime.
float3 evalBRDF(ShadingData sd, float3 L) { return float3(0); }

#if USE_VISCACHE
import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.ShadingCV;
#endif

// ---------------------------------------------------------------------------
// Main kernel: for each pixel, evaluate the RTXDI-selected light sample.
// ---------------------------------------------------------------------------
[numthreads(8, 8, 1)]
void csFinalShading(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    float3 color = float3(0);

    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (hitInfo.isValid() && hitInfo.getType() == HitType::Triangle)
    {
        float3 camPos = gScene.camera.getPosition();
        TriangleHit tri = hitInfo.getTriangleHit();
        VertexData v = gScene.getVertexData(tri);
        float3 viewDir = normalize(camPos - v.posW);
        uint materialID = gScene.getMaterialID(tri.instanceID);

        ShadingData sd = gScene.materials.prepareShadingData(v, materialID, viewDir);

        SampleGenerator sg = SampleGenerator::create(pixel, gRTXDI.frameIndex);

        // Get RTXDI's selected light sample for this pixel
        uint lightIndex;
        float2 lightUV;
        if (gRTXDI.getFinalSample(pixel, lightIndex, lightUV))
        {
            // Evaluate light contribution
            float3 lightPos;
            float3 Li;
            float  G;
            gRTXDI.evalFinalSample(pixel, sd, lightIndex, lightUV,
                                    lightPos, Li, G);

            // Evaluate BSDF at primary hit toward the light
            float3 lightDir = normalize(lightPos - sd.posW);
            let lod = ExplicitLodTextureSampler(0.0f);
            let bsdf = gScene.materials.getBSDF(sd, lod);
            float3 f = bsdf.eval(sd, lightDir, sg);

#if USE_VISCACHE
            // CV+RRR gated visibility (S11.3)
            float3 C = f * Li * G;
            float Vest = evalRevalidationCV(sd.posW, lightPos,
                                             f, Li, G, camPos, sg);
            color = C * Vest;
#else
            // Vanilla: unconditional shadow ray
            float V = traceShadowRay(
                computeRayOrigin(sd.posW, sd.faceN), lightPos);
            color = f * Li * G * V;
#endif
        }

        // Clamp fireflies
        float lum = luminance(color);
        if (lum > kFireflyClamp) color *= kFireflyClamp / lum;
    }

    gColorOutput[pixel] = float4(color, 1.0f);
}
