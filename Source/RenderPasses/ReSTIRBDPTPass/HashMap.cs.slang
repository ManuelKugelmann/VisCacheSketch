import HashMap;

struct DATA_TYPE {
    uint data[DATA_SIZE];
};

cbuffer CB {
    HashMap<DATA_TYPE> gHashMap;
}

[shader("compute")]
[numthreads(256, 1, 1)]
void ComputeHashMapOffsets(uint3 index: SV_DispatchThreadID) {
    gHashMap.ComputeCellOffset(index.x);
}

[shader("compute")]
[numthreads(256, 1, 1)]
void SortHashMapData(uint3 index: SV_DispatchThreadID) {
    gHashMap.SortData(index.x);
}
