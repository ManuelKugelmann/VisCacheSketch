/***************************************************************************
 * WSReservoir.slang
 *
 * §9.4 World-space ReSTIR DI reservoir — single-cell slot, 32 bytes.
 * Independent system from VisCache: keyed by WS-ReSTIR's own posA
 * quantization (gWSCellLevel into the shared posA cascade). Fingerprint disambiguates
 * collisions in the same way as VHFEntry.
 *
 * Stays algorithm-agnostic about which scene light system selected the
 * sample — `lightIdx` is interpreted by the host PathTracer (e.g. as a
 * Falcor LightCollection emissive triangle index).
 ***************************************************************************/

#pragma once

// 32 bytes. Identity = (lightType, lightIndex, uv-or-dir):
//   lightType  : LightType enum (high 8 bits of lightTypeIndex).
//   lightIndex : low 24 bits — analytic-light or emissive-triangle index.
//   payload    : packed barys for emissive (16:16 unorm), oct-packed dir for
//                env (16:16 unorm), 0 for analytic.
// The read path re-evaluates Li at the new shading point from this triple,
// independent of the surface that originally selected the sample.
struct WSReservoir
{
    uint   fingerprint;       ///< 32-bit posA-fingerprint. 0 = empty sentinel.
    uint   lightTypeIndex;    ///< (lightType << 24) | (lightIndex & 0x00FFFFFFu).
    uint   payload;           ///< barys (emissive) | dirOct (env) | 0 (analytic).
    float  targetPdf;         ///< p̂ at selection time (luminance of chosen contribution).
    float  M;                 ///< Accumulated sample count (capped at gWSMCap).
    float  W;                 ///< Unbiased weight: w_sum_total / (p̂(y) * M).
    uint   frameLastUpdated;  ///< gFrameCount at last write — staleness diagnostic.
    uint   normalOct;         ///< Oct-packed shading normal at write site. 0 = unset.
};

// ---------------------------------------------------------------------------
// Empty-slot test. fingerprint=0 means "no reservoir has claimed this slot".
// ---------------------------------------------------------------------------
bool wsReservoirIsEmpty(WSReservoir r) { return r.fingerprint == 0u; }

// ---------------------------------------------------------------------------
// Octahedral direction pack/unpack — 16:16 fixed-point on the oct map.
// ~1.5° angular precision, fits in one uint. Standard formulation.
// ---------------------------------------------------------------------------
uint wsPackDirOct(float3 d)
{
    d /= max(abs(d.x) + abs(d.y) + abs(d.z), 1e-6f);
    float2 oct = (d.z >= 0.f)
        ? d.xy
        : (1.f - abs(d.yx)) * float2(d.x >= 0.f ? 1.f : -1.f, d.y >= 0.f ? 1.f : -1.f);
    uint x = uint((saturate(oct.x * 0.5f + 0.5f)) * 65535.f + 0.5f);
    uint y = uint((saturate(oct.y * 0.5f + 0.5f)) * 65535.f + 0.5f);
    return x | (y << 16);
}

float3 wsUnpackDirOct(uint packed)
{
    float ox = float(packed & 0xFFFFu) * (1.f / 65535.f) * 2.f - 1.f;
    float oy = float(packed >> 16)     * (1.f / 65535.f) * 2.f - 1.f;
    float3 d = float3(ox, oy, 1.f - abs(ox) - abs(oy));
    if (d.z < 0.f)
    {
        float xs = ox >= 0.f ? 1.f : -1.f;
        float ys = oy >= 0.f ? 1.f : -1.f;
        d.xy = (1.f - abs(d.yx)) * float2(xs, ys);
    }
    return normalize(d);
}

// ---------------------------------------------------------------------------
// (u,v) pack/unpack — 16:16 unorm. Used for triangle barycentrics.
// ---------------------------------------------------------------------------
uint wsPackUV(float2 uv)
{
    uint x = uint(saturate(uv.x) * 65535.f + 0.5f);
    uint y = uint(saturate(uv.y) * 65535.f + 0.5f);
    return x | (y << 16);
}
float2 wsUnpackUV(uint packed)
{
    float u = float(packed & 0xFFFFu) * (1.f / 65535.f);
    float v = float(packed >> 16)     * (1.f / 65535.f);
    return float2(u, v);
}

// ---------------------------------------------------------------------------
// (lightType, lightIndex) pack/unpack into a single uint.
// type in upper 8 bits (we never have >256 light types), idx in lower 24
// bits (sufficient for ~16M emissive triangles).
// ---------------------------------------------------------------------------
uint wsPackLightTypeIndex(uint lightType, uint lightIndex)
{
    return ((lightType & 0xFFu) << 24) | (lightIndex & 0x00FFFFFFu);
}
uint wsUnpackLightType(uint pkd)  { return (pkd >> 24) & 0xFFu; }
uint wsUnpackLightIndex(uint pkd) { return pkd & 0x00FFFFFFu; }

// ---------------------------------------------------------------------------
// Construct an empty reservoir for the given fingerprint.
// ---------------------------------------------------------------------------
WSReservoir wsReservoirInit(uint fingerprint)
{
    WSReservoir r;
    r.fingerprint      = fingerprint;
    r.lightTypeIndex   = 0u;
    r.payload          = 0u;
    r.targetPdf        = 0.0f;
    r.M                = 0.0f;
    r.W                = 0.0f;
    r.frameLastUpdated = 0u;
    r.normalOct        = 0u;
    return r;
}
