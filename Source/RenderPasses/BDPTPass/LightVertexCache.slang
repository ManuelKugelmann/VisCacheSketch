#include "BitfieldMacros.slangh"
import Scene.HitInfo;
import PathReservoir; // for PackedPathVertex

struct LightSubpathVertex {
    LightSubpathData mLightSubpath = {};
    PackedPathVertex mVertex = {};
    float3 mThroughput = 0;
    uint pad;
    RecursiveMisState mis = {};

    property uint mBounces {
        get { return mLightSubpath.mVertexCount - 2; }
    }
    property uint mDiffuseBounces {
        get { return mLightSubpath.mDiffuseBounces; }
        set { mLightSubpath.mDiffuseBounces = newValue; }
    }

    float3 GetDirIn() { return -mVertex.mRayDirection; }
};
static const uint LightSubpathVertexSize = sizeof(LightSubpathVertex);

struct LightVertexCache {
    RWStructuredBuffer<LightSubpathVertex> lightVertices; ///< Diffuse light sub-path vertices.
    RWStructuredBuffer<uint> lightVertexCount;            ///< Number of items in lightVertices.

    uint size()
    {
        return lightVertexCount[0];
    }

    __subscript(uint i) -> LightSubpathVertex
    {
        get { return lightVertices[i]; }
        set { lightVertices[i] = newValue; }
    }

    uint Insert(const LightSubpathVertex v)
    {
        uint i;
        InterlockedAdd(lightVertexCount[0], 1, i);
        lightVertices[i] = v;
        return i;
    }
}
