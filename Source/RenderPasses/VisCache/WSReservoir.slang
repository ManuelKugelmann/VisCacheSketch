/***************************************************************************
 * WSReservoir.slang
 *
 * §9.4 World-space ReSTIR DI reservoir — single-cell slot, 32 bytes.
 * Indexed via VisCache's posA cascade with a level offset (gWSLevelOffset);
 * fingerprint disambiguates collisions in the same way as VHFEntry.
 *
 * Stays algorithm-agnostic about which scene light system selected the
 * sample — `lightIdx` is interpreted by the host PathTracer (e.g. as a
 * Falcor LightCollection emissive triangle index).
 ***************************************************************************/

#pragma once

// 32 bytes. Field order is laid out for natural 4-byte alignment.
// Identity is stored as a shadow-ray pin (dir + distance) rather than a
// light-system-specific (lightIdx, uv) pair — keeps the reservoir
// agnostic to whether the chosen sample was analytic, emissive, or
// envmap. Read path re-traces in `dirOct` for `distance` and evaluates
// emission at the hit (or the envmap miss).
struct WSReservoir
{
    uint   fingerprint;       ///< 32-bit posA-fingerprint of the cell owning this slot.
                              ///< 0 = empty slot sentinel.
    uint   dirOct;            ///< Octahedral-packed direction to the chosen light point.
    float  distance;          ///< Shadow-ray length (cached visibility distance).
    float  targetPdf;         ///< p̂ at selection time (luminance of chosen contribution).
    float  M;                 ///< Accumulated sample count (capped at gWSMCap).
    float  W;                 ///< Unbiased weight: (1 / p̂(y)) * (1 / M) * w_sum.
    uint   frameLastUpdated;  ///< gFrameCount at last write — stale-detection / debug.
    uint   lightType;         ///< LightType of the chosen sample (analytic / emissive / env).
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
// Construct an empty reservoir for the given fingerprint.
// ---------------------------------------------------------------------------
WSReservoir wsReservoirInit(uint fingerprint)
{
    WSReservoir r;
    r.fingerprint      = fingerprint;
    r.dirOct           = 0u;
    r.distance         = 0.0f;
    r.targetPdf        = 0.0f;
    r.M                = 0.0f;
    r.W                = 0.0f;
    r.frameLastUpdated = 0u;
    r.lightType        = 0u;
    return r;
}
