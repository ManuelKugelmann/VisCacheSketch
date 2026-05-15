/***************************************************************************
 # Copyright (c) 2015-22, NVIDIA CORPORATION. All rights reserved.
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
__exported import Rendering.Materials.TexLODTypes;

/** Translation of defines set by the host to compile-time constants used to
    configure the path tracer without overhead from dynamic control flow.
    This will eventually be replaced by specialization constants in Slang.
*/

#ifndef SAMPLES_PER_PIXEL
#error StaticParams.slang is missing defines
#endif

static const uint kUseViewDir = USE_VIEW_DIR;
static const uint kSamplesPerPixel = SAMPLES_PER_PIXEL;
static const uint kMaxSurfaceBounces = MAX_SURFACE_BOUNCES;
static const uint kMaxDiffuseBounces = MAX_DIFFUSE_BOUNCES;
static const uint kMaxSpecularBounces = MAX_SPECULAR_BOUNCES;
static const uint kMaxTransmissionBounces = MAX_TRANSMISSON_BOUNCES;
static const bool kAdjustShadingNormals = ADJUST_SHADING_NORMALS != 0;
static const bool kUseBSDFSampling = USE_BSDF_SAMPLING != 0;
static const bool kUseNEE = USE_NEE != 0;
static const bool kUseMIS = USE_MIS != 0;
static const bool kUseRussianRoulette = USE_RUSSIAN_ROULETTE != 0;
static const bool kUseRTXDI = USE_RTXDI != 0;
static const bool kUseAlphaTest = USE_ALPHA_TEST != 0;
static const bool kUseLightsInDielectricVolumes = USE_LIGHTS_IN_DIELECTRIC_VOLUMES != 0;
static const bool kDisableCaustics = DISABLE_CAUSTICS != 0;
static const TexLODMode kPrimaryLodMode = TexLODMode(PRIMARY_LOD_MODE);
static const bool kUseNRDDemodulation = USE_NRD_DEMODULATION != 0;
static const uint kColorFormat = COLOR_FORMAT;
static const uint kMISHeuristic = MIS_HEURISTIC;
static const float kMISPowerExponent = MIS_POWER_EXPONENT;

// RTXDI-parity category-quota K-RIS candidate counts. When non-zero,
// generateInitialCandidatesFresh() adds dedicated env/inf/BRDF streams on
// top of the gInitialCandidates uniform stream (which routes through
// selectLightType). Set initialCandidates=0 to disable the uniform
// stream entirely and run pure category-quota K-RIS (RTXDI parity).
#ifndef ENV_CANDIDATE_COUNT
#define ENV_CANDIDATE_COUNT 0
#endif
#ifndef INFINITE_CANDIDATE_COUNT
#define INFINITE_CANDIDATE_COUNT 0
#endif
#ifndef BRDF_CANDIDATE_COUNT
#define BRDF_CANDIDATE_COUNT 0
#endif
static const uint kEnvCandidateCount      = ENV_CANDIDATE_COUNT;
static const uint kInfiniteCandidateCount = INFINITE_CANDIDATE_COUNT;
static const uint kBrdfCandidateCount     = BRDF_CANDIDATE_COUNT;
