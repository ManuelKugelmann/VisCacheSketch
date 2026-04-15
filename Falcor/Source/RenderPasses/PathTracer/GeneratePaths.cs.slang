/***************************************************************************
 # Copyright (c) 2015-24, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
import Utils.Attributes;
import Utils.Color.ColorHelpers;
import Rendering.RTXDI.RTXDI;
import RenderPasses.Shared.Denoising.NRDBuffers;
import RenderPasses.Shared.Denoising.NRDConstants;
import LoadShadingData;
import NRDHelpers;
import PathTracer;
import PathState;
import ColorType;
import Params;

// Shared memory variables.
// TODO: Can we declare these inside PathGenerator?
static const uint kWarpCount = (kScreenTileDim.x * kScreenTileDim.y) / 32;

// TODO: Replace explicitly declared size by compile-time constant when it works. For now assume tile is always 16x16!
groupshared uint gSamplesOffset[8 /* kWarpCount */];

// Subframe N×N Bayer pixel interleaving. 1 = full frame (no gate),
// 2 = 2×2 (4 subframes), 4 = 4×4 (16 subframes). Reduced-dispatch shader
// remaps threadID to full-resolution pixel via subframeRemap() in Params.slang.
#ifndef VISCACHE_SUBFRAME_N
#define VISCACHE_SUBFRAME_N 1
#endif
static const uint kVisCacheSubframeN = VISCACHE_SUBFRAME_N;

/** Helper struct for generating paths in screen space.

    The dispatch size is one thread group per screen tile. A warp is assumed to be 32 threads.
    Within a thread group, the threads are linearly indexed and mapped to pixels in Morton order.

    Output sample buffer
    --------------------

    For each pixel that belongs to the background, and hence does not need to be path traced,
    we directly evaluate the background color and write all samples to the output sample buffers.

    The output sample buffers are organized by tiles in scanline order. Within tiles,
    the pixels are enumerated in Morton order with all samples for a pixel stored consecutively.

    When the number of samples/pixel is not fixed, we additionally write a 2D lookup table,
    for each pixel storing the tile-local offset to where the first sample is stored.
    Based on this information, subsequent passes can easily find the location of a given sample.
*/
struct PathGenerator
{
    // Resources
    PathTracerParams params;                        ///< Runtime parameters.

    Texture2D<PackedHitInfo> vbuffer;               ///< Fullscreen V-buffer for the primary hits.
    Texture2D<float3> viewDir;                      ///< Optional view direction. Only valid when kUseViewDir == true.
    Texture2D<uint> sampleCount;                    ///< Optional input sample count buffer. Only valid when kSamplesPerPixel == 0.
    RWTexture2D<uint> sampleOffset;                 ///< Output offset into per-sample buffers. Only valid when kSamplesPerPixel == 0.

    RWStructuredBuffer<ColorType> sampleColor;      ///< Output per-sample color if kSamplesPerPixel != 1.
    RWStructuredBuffer<GuideData> sampleGuideData;  ///< Output per-sample guide data.
    NRDBuffers outputNRD;                           ///< Output NRD data.

    RWTexture2D<float4> outputColor;                ///< Output color buffer if kSamplesPerPixel == 1.

    // Render settings that depend on the scene.
    // TODO: Move into scene defines.
    static const bool kUseEnvLight = USE_ENV_LIGHT != 0;
    static const bool kUseCurves = USE_CURVES != 0;

    // Additional specialization.
    static const bool kOutputGuideData = OUTPUT_GUIDE_DATA != 0;

    /** Entry point for path generator.
        \param[in] tileID Tile ID in x and y on screen.
        \param[in] threadIdx Thread index within the tile.
    */
    void execute(const uint2 tileID, const uint threadIdx)
    {
        // Map thread to pixel via Morton order within tile.
        //
        // Dispatch strategy depends on kSamplesPerPixel:
        //   - Fixed spp (kSamplesPerPixel > 0): host dispatches reduced (ceil(W/N)×ceil(H/N));
        //     shader Bayer-remaps threadID to full-resolution pixel. Each active thread
        //     corresponds to an active-slot pixel (no waste).
        //   - Variable spp (kSamplesPerPixel == 0): host dispatches full; shader uses
        //     pixel = reducedPixel and zeros spp on inactive Bayer slots. The per-warp
        //     prefix sum for sample packing requires all threads in a group to share a
        //     full tile, which the reduced+remap path can't guarantee → full dispatch.
        const uint2 tileOffset = tileID << kScreenTileBits;
        const uint2 reducedPixel = deinterleave_8bit(threadIdx) + tileOffset;
        const uint2 pixel = (kSamplesPerPixel > 0)
            ? subframeRemap(reducedPixel, params.subframeIdx, kVisCacheSubframeN)
            : reducedPixel;

        // Process each pixel.
        // If we don't hit any surface then the background will be evaluated and written out directly.
        Ray cameraRay;
        bool hitSurface = false;
        uint spp = 0;

        // Note: Do not terminate threads for out-of-bounds pixels because we need all threads active for the prefix sum pass below.
        if (all(pixel < params.frameDim))
        {
            // Determine number of samples at the current pixel.
            // This is either a fixed number or loaded from the sample count texture.
            // TODO: We may want to use a nearest sampler to allow the texture to be of arbitrary dimension.
            spp = kSamplesPerPixel > 0 ? kSamplesPerPixel : min(sampleCount[pixel], kMaxSamplesPerPixel);

            // Variable-spp + subframe gate: zero spp for inactive Bayer slots so the
            // pass falls through as if this pixel has no samples this dispatch. Fixed
            // spp uses reduced dispatch instead (no inactive threads to gate).
            if (kSamplesPerPixel == 0 && kVisCacheSubframeN > 1
                && !isActiveSubframeSlot(pixel, params.subframeIdx, kVisCacheSubframeN))
            {
                spp = 0;
            }

            // Compute the primary ray.
            cameraRay = gScene.camera.computeRayPinhole(pixel, params.frameDim);
            if (kUseViewDir) cameraRay.dir = -viewDir[pixel];

            // Load the primary hit from the V-buffer.
            const HitInfo hit = unpackHitInfo(vbuffer[pixel]);
            hitSurface = hit.isValid();

            // Prepare per-pixel surface data for RTXDI.
            if (kUseRTXDI)
            {
                bool validSurface = false;
                if (hitSurface)
                {
                    ShadingData sd = loadShadingData(hit, cameraRay.origin, cameraRay.dir);

                    // Create material instance and query its properties.
                    let lod = ExplicitLodTextureSampler(0.f);
                    let hints = getMaterialInstanceHints(hit, true /* primary hit */);
                    let mi = gScene.materials.getMaterialInstance(sd, lod, hints);
                    let bsdfProperties = mi.getProperties(sd);

                    // Check for BSDF lobes that RTXDI can sample.
                    uint lobeTypes = mi.getLobeTypes(sd);
                    validSurface = (lobeTypes & (uint)LobeType::NonDeltaReflection) != 0;

                    if (validSurface)
                    {
                        // RTXDI uses a simple material model with only diffuse and specular reflection lobes.
                        // We query the BSDF for the diffuse albedo and specular reflectance.
                        gRTXDI.setSurfaceData(pixel, sd.computeRayOrigin(), bsdfProperties.guideNormal, bsdfProperties.diffuseReflectionAlbedo, bsdfProperties.specularReflectance, bsdfProperties.roughness);
                    }
                }
                if (!validSurface) gRTXDI.setInvalidSurfaceData(pixel);
            }
        }

        // Perform a reduction over the tile to determine the number of samples required.
        // This is done via wave ops and shared memory.
        // The write offsets are given by prefix sums over the threads.
        const uint warpIdx = threadIdx >> 5;

        // Calculate the sample counts over the warp.
        // The first thread in each warp writes the results to shared memory.
        {
            uint samples = WaveActiveSum(spp);

            if (WaveIsFirstLane())
            {
                gSamplesOffset[warpIdx] = samples;
            }
        }
        GroupMemoryBarrierWithGroupSync();

        // Compute the prefix sum over the warp totals in shared memory.
        // The first N threads in the thread group perform this computation.
        if (threadIdx < kWarpCount)
        {
            // Compute the prefix sum over the sample counts.
            uint samples = gSamplesOffset[threadIdx];
            gSamplesOffset[threadIdx] = WavePrefixSum(samples);
        }
        GroupMemoryBarrierWithGroupSync();

        if (all(pixel < params.frameDim))
        {
            // Compute the output sample index.
            // Index by the pixel's actual full-resolution tile — at N>1 the Bayer-
            // remapped `pixel` can fall into a different full tile than the reduced
            // `tileID` we were dispatched under. Must match ResolvePass's reader
            // (Params.slang::getSampleOffset), which keys on `pixel >> kScreenTileBits`.
            const uint2 fullTile = pixel >> kScreenTileBits;
            const uint outTileOffset = params.getTileOffset(fullTile);
            uint outIdx = 0;

            if (kSamplesPerPixel > 0)
            {
                const uint tileBits = kScreenTileBits.x + kScreenTileBits.y;
                const uint pixelIdx = interleave_16bit(pixel) & ((1 << tileBits) - 1);
                outIdx = outTileOffset + pixelIdx * kSamplesPerPixel;
            }
            else
            {
                // TODO: variable-spp with N>1 is not yet correct — the prefix sum is
                // keyed on threadIdx within the reduced tile, but pixels may land in
                // different full tiles, so sampleOffset[pixel] can collide. Only fixed
                // spp is supported with subframe gate for now.
                uint outSampleOffset = gSamplesOffset[warpIdx] + WavePrefixSum(spp);
                outIdx = outTileOffset + outSampleOffset;
                sampleOffset[pixel] = outSampleOffset;
            }

            if (!hitSurface)
            {
                // Write background pixels.
                writeBackground(pixel, spp, outIdx, cameraRay.dir);
            }
        }
    }

    void writeBackground(const uint2 pixel, const uint spp, const uint outIdx, const float3 dir)
    {
        // Evaluate background color for the current pixel.
        float3 color = float3(0.f);
        if (kUseEnvLight)
        {
            color = gScene.envMap.eval(dir);
        }

        // Write color and denoising guide data for all samples in pixel.
        // For the special case of fixed 1 spp we write the color directly to the output texture.
        if (kSamplesPerPixel == 1)
        {
            outputColor[pixel] = float4(color, 1.f);
        }

        for (uint i = 0; i < spp; i++)
        {
            if (kSamplesPerPixel != 1)
            {
                sampleColor[outIdx + i].set(color);
            }

            if (kOutputGuideData)
            {
                PathTracer::setBackgroundGuideData(sampleGuideData[outIdx + i], dir, color);
            }

            if (kOutputNRDData)
            {
                outputNRD.sampleRadiance[outIdx + i] = {};
                outputNRD.sampleHitDist[outIdx + i] = kNRDInvalidPathLength;
                outputNRD.sampleEmission[outIdx + i] = 0.f;
                outputNRD.sampleReflectance[outIdx + i] = 1.f;
            }
        }

        if (kOutputNRDData)
        {
            outputNRD.primaryHitEmission[pixel] = float4(color, 1.f);
            outputNRD.primaryHitDiffuseReflectance[pixel] = 0.f;
            outputNRD.primaryHitSpecularReflectance[pixel] = 0.f;
        }

        if (kOutputNRDAdditionalData)
        {
            writeNRDDeltaReflectionGuideBuffers(outputNRD, kUseNRDDemodulation, pixel, 0.f, 0.f, -dir, 0.f, kNRDInvalidPathLength, kNRDInvalidPathLength);
            writeNRDDeltaTransmissionGuideBuffers(outputNRD, kUseNRDDemodulation, pixel, 0.f, 0.f, -dir, 0.f, kNRDInvalidPathLength, 0.f);
        }
    }
};

cbuffer CB
{
    PathGenerator gPathGenerator;
}

// TODO: Replace by compile-time uint2 constant when it works in Slang.
[numthreads(256 /* kScreenTileDim.x * kScreenTileDim.y */, 1, 1)]
void main(
    uint3 groupID : SV_GroupID,
    uint3 groupThreadID : SV_GroupThreadID)
{
    gPathGenerator.execute(groupID.xy, groupThreadID.x);
}
