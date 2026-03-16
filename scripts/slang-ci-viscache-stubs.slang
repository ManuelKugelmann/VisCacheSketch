// slang-ci-viscache-stubs.slang — Consumer-provided stubs for VisCache CI.
//
// VisCache shaders (ShadingCV.slang, RevalidationCommon.slang, VisCacheTracing.slang)
// are library modules consumed by the host render pass.  The host provides
// ShadingData, evalBRDF(), traceShadowRay(), etc.  For offline CI compilation
// we provide lightweight stubs here.
//
// NOT shipped in the build — CI only.

#pragma once

import Utils.Color.ColorHelpers;       // luminance()
import Utils.Sampling.SampleGenerator; // SampleGenerator, sampleNext1D()

// Consumer-provided shadow ray function stubs.
float traceShadowRay(float3 origin, float3 dir, float distance) { return 1.f; }
float traceShadowRay(float3 origin, float3 target) { return 1.f; }

// ShadingCV.slang consumer-provided stubs.
struct ShadingData { float3 posW; };
float3 evalBRDF(ShadingData sd, float3 L) { return float3(1.f); }
