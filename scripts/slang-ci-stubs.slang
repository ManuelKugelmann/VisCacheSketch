// slang-ci-stubs.slang — Stub declarations for CI compilation.
//
// These functions/types are normally provided by the consumer pass that
// imports our shader modules.  We declare them here so slangc can
// type-check our code in isolation.
//
// NOT shipped in the build — CI only.

#pragma once

import Utils.Color.ColorHelpers;       // luminance()
import Utils.Sampling.SampleGenerator; // SampleGenerator, sampleNext1D()

// Consumer-provided shadow ray function stubs.
// Signatures match what VisCacheTracing.slang / RevalidationCommon.slang expect.
float traceShadowRay(float3 origin, float3 dir, float distance) { return 1.f; }
float traceShadowRay(float3 origin, float3 target) { return 1.f; }

// ShadingCV.slang consumer-provided stubs
struct ShadingData { float3 posW; };
float3 evalBRDF(ShadingData sd, float3 L) { return float3(1.f); }
