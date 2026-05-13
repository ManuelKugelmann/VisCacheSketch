/***************************************************************************
 # CacheHash.slang — generic cache-primitive math.
 #
 # PCG hash family (Jarzynski & Olano, JCGT 2020) + octahedral direction
 # encoding + 6-axis normal binning. Pure functions — no cbuffer access,
 # no USE_VISCACHE guard, no dependency on Falcor render-graph state.
 #
 # Used by: VisCache (cache-table addressing), ReSTIRCommon (Reservoir +
 # CellPool indexing), ReSTIRPTPass (PathReservoirCellPool jitter).
 *************************************************************************/
#pragma once

/// 3D PCG hash. Maps uint3 -> uint3 with strong avalanche.
uint3 pcg3d(uint3 v)
{
    v = v * 1664525u + 1013904223u;
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    v ^= v >> 16u;
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    return v;
}

/// Hash one endpoint: int3 coords + level + salt -> uint.
/// PCG-style: LCG init, 2 rounds of circular cross-mix, XOR-fold.
uint pcgHashEndpoint(int3 q, uint lvl, uint salt)
{
    uint a = uint(q.x) * 1664525u + 1013904223u;
    uint b = uint(q.y) * 1664525u + 1013904223u;
    uint c = uint(q.z) * 1664525u + 1013904223u;
    uint d = lvl        * 1664525u + 1013904223u;
    uint e = salt       * 1664525u + 1013904223u;

    a += b * e;  b += c * a;  c += d * b;  d += e * c;  e += a * d;
    a ^= a >> 16u;  b ^= b >> 16u;  c ^= c >> 16u;  d ^= d >> 16u;  e ^= e >> 16u;
    a += b * e;  b += c * a;  c += d * b;  d += e * c;  e += a * d;

    return a ^ b ^ c ^ d ^ e;
}

// Per-dimension salt constants — each dimension gets its own hash space.
static const uint kSaltA    = 0x12345678u;
static const uint kSaltB    = 0x9E3779B9u;
static const uint kSaltDist = 0x6C62272Eu;

/// Per-dimension hash wrappers.
uint pcgHashA(int3 qa, uint lvlA) { return pcgHashEndpoint(qa, lvlA, kSaltA); }
uint pcgHashB(int3 qb, uint lvlB) { return pcgHashEndpoint(qb, lvlB, kSaltB); }
uint pcgHashDist(uint lvlDist)    { return pcgHashEndpoint(int3(0), lvlDist, kSaltDist); }

/// Combined hash: hashA ^ hashB ^ hashDist ^ salt.
/// salt differentiates address from fingerprint (applied to final output only).
uint pcgHash(int3 qa, int3 qb, uint lvlA, uint lvlB, uint lvlDist, uint salt)
{
    return pcgHashA(qa, lvlA) ^ pcgHashB(qb, lvlB) ^ pcgHashDist(lvlDist) ^ salt;
}

/// 6-axis face-normal bin (±X, ±Y, ±Z = 6 distinct bins). Pure; shared by
/// VisCache, ReSTIRCommon (CellPool/ReservoirIO), and ReSTIRPTPass's
/// PathReservoirCellPool so all world-cell-keyed pools agree on which face
/// a primary hit belongs to.
uint normalBin(float3 n)
{
    float3 a = abs(n);
    int axis = (a.x >= a.y && a.x >= a.z) ? 0 : (a.y >= a.z ? 1 : 2);
    bool pos = n[axis] >= 0.f;
    return uint(axis * 2 + (pos ? 0 : 1));     // 0..5
}

/// Octahedral direction encoding: maps unit sphere -> [-1, 1]² near-uniformly.
/// Used for both IBL direction encoding and dirdist addressing to quantize
/// directions as 2D bins independently of spatial cell size.
/// Reference: Meyer et al. 2010, "On Floating-Point Normal Vectors"
float2 octEncode(float3 n)
{
    float s = abs(n.x) + abs(n.y) + abs(n.z);
    float2 o = n.xy / max(s, 1e-7f);
    if (n.z < 0.f)
        o = (1.f - abs(o.yx)) * float2(o.x >= 0.f ? 1.f : -1.f, o.y >= 0.f ? 1.f : -1.f);
    return o;  // in [-1, 1]²
}
