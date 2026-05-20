struct HashMap<T> {
    RWStructuredBuffer<uint> mCellKeys;        // Current key for each cell
    RWStructuredBuffer<uint> mCellCounters;    // Number of items in cell
    RWStructuredBuffer<uint> mCellDataOffsets; // Index in mData where each cell's data starts
    RWStructuredBuffer<T> mData;
    RWStructuredBuffer<T> mSortedData;
    RWStructuredBuffer<uint2> mDataIndices;    // (cellIndex, indexInCell) for each item in mData
    RWStructuredBuffer<uint> mCounters;   // Number of items in mData, and the prefix sum counter

    uniform uint mMaxSize;
    uniform uint mCellCount;

    __subscript(const uint index) -> T
    {
        get { return mSortedData[index]; }
	}

    uint FindCellIndex<let bInsert : bool>(uint key) {
        key = 1 + key; // always add 1 since 0 is reserved

        // compute index in hash grid
        const uint baseCellIndex = key % mCellCount;

        // resolve hash collisions with linear probing
        for (uint i = 0; i < 32; i++) {
            const uint cellIndex = (baseCellIndex + i) % mCellCount;
            // find cell with matching key, or empty cell if inserting
            if (bInsert) {
                uint prevKey;
                InterlockedCompareExchange(mCellKeys[key], 0, key, prevKey);
                if (prevKey == 0 || prevKey == key)
                    return cellIndex;
            } else {
                if (mCellKeys[cellIndex] == key)
                    return cellIndex;
            }
        }

        // collision resolution failed
        return -1;
    }

    uint2 GetCellDataRange(const uint key) {
        const uint cellIndex = FindCellIndex<false>(key);
        if (cellIndex == -1)
            return -1;

        const uint begin = mCellDataOffsets[cellIndex];
        return uint2(begin, begin + mCellCounters[cellIndex]);
    }

    bool Insert(const uint key, const T data) {
        const uint cellIndex = FindCellIndex<true>(key);
        if (cellIndex == -1)
            return false;

        // get data index
        uint dataIndex;
        InterlockedAdd(mCounters[0], 1, dataIndex);
        if (dataIndex >= mMaxSize)
            return false;

        // append item to cell by incrementing cell counter
        uint indexInCell;
        InterlockedAdd(mCellCounters[cellIndex], 1, indexInCell);

        // store data at data index
        mData[dataIndex] = data;
        mDataIndices[dataIndex] = uint2(cellIndex, indexInCell);
        return true;
    }


    void ComputeCellOffset(const uint cellIndex) {
        if (cellIndex >= mCellCount) return;

        uint offset;
        InterlockedAdd(mCounters[1], mCellCounters[cellIndex], offset);
        mCellDataOffsets[cellIndex] = offset;
    }
    void SortData(const uint dataIndex) {
        if (dataIndex >= mCounters[0]) return;

        const uint2 indices = mDataIndices[dataIndex];
        mSortedData[mCellDataOffsets[indices.x] + indices.y] = mData[dataIndex];
    }
};
