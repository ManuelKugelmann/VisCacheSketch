// ═══════════════════════════════════════════════════════════════════
// VisibilityCache.cs — GPU resource manager for the visibility cache.
//
// Usage:
//   var cache = new VisibilityCache(computeShader);
//   // each frame:
//   cache.Update(cmd, camera);         // bind globals, decay, stats
//   // in your render pass, shaders call VCQueryShadow / VCRecordShadow
//   cache.Dispose();
//
// The class sets all parameters as global shader properties so any
// shader that #includes VisibilityCache.hlsl can use the cache.
// ═══════════════════════════════════════════════════════════════════

using System;
using UnityEngine;
using UnityEngine.Rendering;

public sealed class VisibilityCache : IDisposable
{
    // ─── Configuration ──────────────────────────────────────────

    [Serializable]
    public struct Config
    {
        [Tooltip("Table size as power-of-2 exponent (20 = 1M entries = 8 MB)")]
        [Range(16, 24)] public int tableSizePow2;

        [Tooltip("L0/L1/L2 cell sizes for endpoint A (shading point)")]
        public Vector3 cellSizeA;

        [Tooltip("L0/L1/L2 cell sizes for endpoint B (light/hit)")]
        public Vector3 cellSizeB;

        [Tooltip("L0/L1/L2 angular resolution in octahedral space for infinite endpoints")]
        public Vector3 angularRes;

        [Tooltip("Variance threshold for RR gating")]
        [Range(0.01f, 0.5f)] public float varThreshold;

        [Tooltip("Minimum RR survival probability")]
        [Range(0.01f, 0.5f)] public float pMin;

        [Tooltip("Contribution ceiling for firefly-adaptive p_min")]
        public float fireflyBudget;

        [Tooltip("Min pixel footprint for LOD gating")]
        public float minPixels;

        [Tooltip("Max pixel footprint for LOD gating")]
        public float maxPixels;

        [Tooltip("Frames for full table decay (0 = disabled)")]
        [Range(0, 600)] public int decayPeriod;

        [Tooltip("Decay strength as right-shift (1=halve, 2=quarter, 3=eighth)")]
        [Range(1, 4)] public int decayShift;

        public static Config Default => new Config
        {
            tableSizePow2 = 20,             // 1M entries, 8 MB
            cellSizeA     = new Vector3(10f, 1.25f, 0.08f),
            cellSizeB     = new Vector3(10f, 2.5f,  0.62f),
            angularRes    = new Vector3(0.5f, 0.125f, 0.03125f),
            varThreshold  = 0.1f,
            pMin          = 0.05f,
            fireflyBudget = 10f,
            minPixels     = 4f,
            maxPixels     = 64f,
            decayPeriod   = 60,
            decayShift    = 3,              // subtract 1/8 per pass
        };
    }

    // ─── Public state ───────────────────────────────────────────

    public struct Stats
    {
        public uint inserts, evictions, misses, decays, probes, lookups;

        public float LoadPressure =>
            inserts > 0 ? (float)evictions / inserts : 0f;
        public float CacheEffectiveness =>
            lookups > 0 ? 1f - (float)misses / lookups : 0f;
        public float AvgProbeDepth =>
            inserts > 0 ? (float)probes / inserts : 0f;
    }

    public Stats LastStats { get; private set; }
    public Config Cfg { get; set; }
    public int TableSize { get; }

    // ─── Private resources ──────────────────────────────────────

    readonly ComputeShader _cs;
    readonly int _kernelClear, _kernelDecay, _kernelStatsClear;
    GraphicsBuffer _tableBuffer;
    GraphicsBuffer _statsBuffer;
    uint _frame;
    bool _disposed;
    bool _needsClear;
    bool _statsRequested;

    // Auto-tune decay
    float _smoothedPressure;
    int _effectiveDecayPeriod;

    // Shader property IDs (cached)
    static readonly int s_Table        = Shader.PropertyToID("_VCTable");
    static readonly int s_Stats        = Shader.PropertyToID("_VCStats");
    static readonly int s_TableSize    = Shader.PropertyToID("_VCTableSize");
    static readonly int s_TableMask    = Shader.PropertyToID("_VCTableMask");
    static readonly int s_CameraPos    = Shader.PropertyToID("_VCCameraPos");
    static readonly int s_TanHalfFov   = Shader.PropertyToID("_VCTanHalfFov");
    static readonly int s_ScreenHeight = Shader.PropertyToID("_VCScreenHeight");
    static readonly int s_MinPixels    = Shader.PropertyToID("_VCMinPixels");
    static readonly int s_MaxPixels    = Shader.PropertyToID("_VCMaxPixels");
    static readonly int s_VarThreshold = Shader.PropertyToID("_VCVarThreshold");
    static readonly int s_PMin         = Shader.PropertyToID("_VCPMin");
    static readonly int s_FireflyBudget= Shader.PropertyToID("_VCFireflyBudget");
    static readonly int s_CellA        = Shader.PropertyToID("_VCCellA");
    static readonly int s_CellB        = Shader.PropertyToID("_VCCellB");
    static readonly int s_AngularRes   = Shader.PropertyToID("_VCAngularRes");
    static readonly int s_Frame        = Shader.PropertyToID("_VCFrame");
    static readonly int s_DecayOffset  = Shader.PropertyToID("_VCDecayOffset");
    static readonly int s_DecayCount   = Shader.PropertyToID("_VCDecayCount");
    static readonly int s_DecayShift   = Shader.PropertyToID("_VCDecayShift");

    // ─── Construction / Disposal ────────────────────────────────

    public VisibilityCache(ComputeShader computeShader, Config? config = null)
    {
        _cs  = computeShader ? computeShader
             : throw new ArgumentNullException(nameof(computeShader));
        Cfg  = config ?? Config.Default;

        TableSize = 1 << Mathf.Clamp(Cfg.tableSizePow2, 16, 24);
        _effectiveDecayPeriod = Cfg.decayPeriod;

        // Find kernels — fail fast.
        _kernelClear      = MustFindKernel("CSVCClear");
        _kernelDecay      = MustFindKernel("CSVCDecay");
        _kernelStatsClear = MustFindKernel("CSVCStatsClear");

        // Allocate GPU buffers.
        // Table: 2 uints per entry (fingerprint + packed).
        _tableBuffer = new GraphicsBuffer(
            GraphicsBuffer.Target.Structured,
            TableSize * 2,
            sizeof(uint));
        _tableBuffer.name = "VCTable";

        // Stats: 6 uint counters.
        _statsBuffer = new GraphicsBuffer(
            GraphicsBuffer.Target.Structured,
            6,
            sizeof(uint));
        _statsBuffer.name = "VCStats";

        Debug.Log($"[VisibilityCache] {TableSize} entries " +
                  $"({TableSize * 8 / (1024 * 1024)} MB)");

        _needsClear = true;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _tableBuffer?.Release();
        _statsBuffer?.Release();
        _tableBuffer = null;
        _statsBuffer = null;
    }

    // ─── Per-Frame Update ───────────────────────────────────────

    /// <summary>
    /// Call once per frame before any rendering that uses the cache.
    /// Binds all globals, dispatches decay and stats reset.
    /// </summary>
    public void Update(CommandBuffer cmd, Camera camera)
    {
        if (_disposed)
            throw new ObjectDisposedException(nameof(VisibilityCache));
        if (cmd == null)
            throw new ArgumentNullException(nameof(cmd));
        if (camera == null)
            throw new ArgumentNullException(nameof(camera));

        BindGlobals(cmd, camera);
        if (_needsClear)
        {
            Clear(cmd);
            _needsClear = false;
        }
        RequestStatsReadback(cmd); // cmd-sequenced: reads before clear
        DispatchStatsClear(cmd);
        DispatchDecay(cmd);
        _frame++;
    }

    /// <summary>
    /// Clear entire table. Call on scene load or major camera cut.
    /// </summary>
    public void Clear(CommandBuffer cmd)
    {
        if (_disposed)
            throw new ObjectDisposedException(nameof(VisibilityCache));

        BindBuffersToCompute(cmd);
        cmd.SetComputeIntParam(_cs, s_TableSize, TableSize);
        cmd.DispatchCompute(_cs, _kernelClear,
            CeilDiv(TableSize, 64), 1, 1);
    }

    // ─── Internals ──────────────────────────────────────────────

    void BindGlobals(CommandBuffer cmd, Camera camera)
    {
        // Buffers (global so all shaders see them).
        cmd.SetGlobalBuffer(s_Table, _tableBuffer);
        cmd.SetGlobalBuffer(s_Stats, _statsBuffer);

        // Table geometry.
        cmd.SetGlobalInt(s_TableSize, TableSize);
        cmd.SetGlobalInt(s_TableMask, TableSize - 1);

        // Camera.
        cmd.SetGlobalVector(s_CameraPos,
            (Vector4)camera.transform.position);
        cmd.SetGlobalFloat(s_TanHalfFov,
            Mathf.Tan(camera.fieldOfView * 0.5f * Mathf.Deg2Rad));
        cmd.SetGlobalFloat(s_ScreenHeight, camera.pixelHeight);

        // LOD gating.
        cmd.SetGlobalFloat(s_MinPixels, Cfg.minPixels);
        cmd.SetGlobalFloat(s_MaxPixels, Cfg.maxPixels);

        // CV+RRR parameters.
        cmd.SetGlobalFloat(s_VarThreshold,  Cfg.varThreshold);
        cmd.SetGlobalFloat(s_PMin,          Cfg.pMin);
        cmd.SetGlobalFloat(s_FireflyBudget, Cfg.fireflyBudget);

        // Cell sizes (Vector4 with xyz = L0,L1,L2).
        cmd.SetGlobalVector(s_CellA,
            new Vector4(Cfg.cellSizeA.x, Cfg.cellSizeA.y, Cfg.cellSizeA.z, 0));
        cmd.SetGlobalVector(s_CellB,
            new Vector4(Cfg.cellSizeB.x, Cfg.cellSizeB.y, Cfg.cellSizeB.z, 0));
        cmd.SetGlobalVector(s_AngularRes,
            new Vector4(Cfg.angularRes.x, Cfg.angularRes.y, Cfg.angularRes.z, 0));

        cmd.SetGlobalInt(s_Frame, (int)_frame);
    }

    void DispatchDecay(CommandBuffer cmd)
    {
        int period = _effectiveDecayPeriod;
        if (period <= 0) return;

        int stride = TableSize / period;
        if (stride <= 0) return;

        int offset = (int)(_frame % (uint)period) * stride;

        BindBuffersToCompute(cmd);
        cmd.SetComputeIntParam(_cs, s_TableSize,   TableSize);
        cmd.SetComputeIntParam(_cs, s_DecayOffset,  offset);
        cmd.SetComputeIntParam(_cs, s_DecayCount,   stride);
        cmd.SetComputeIntParam(_cs, s_DecayShift,
            Mathf.Clamp(Cfg.decayShift, 1, 4));
        cmd.DispatchCompute(_cs, _kernelDecay,
            CeilDiv(stride, 64), 1, 1);
    }

    void DispatchStatsClear(CommandBuffer cmd)
    {
        BindBuffersToCompute(cmd);
        cmd.DispatchCompute(_cs, _kernelStatsClear, 1, 1, 1);
    }

    void BindBuffersToCompute(CommandBuffer cmd)
    {
        // Compute kernels need explicit per-kernel buffer binding.
        cmd.SetComputeBufferParam(_cs, _kernelClear,      s_Table, _tableBuffer);
        cmd.SetComputeBufferParam(_cs, _kernelClear,      s_Stats, _statsBuffer);
        cmd.SetComputeBufferParam(_cs, _kernelDecay,      s_Table, _tableBuffer);
        cmd.SetComputeBufferParam(_cs, _kernelDecay,      s_Stats, _statsBuffer);
        cmd.SetComputeBufferParam(_cs, _kernelStatsClear, s_Stats, _statsBuffer);
    }

    // ─── Async Stats Readback ───────────────────────────────────

    void RequestStatsReadback(CommandBuffer cmd)
    {
        if (_statsRequested) return;
        _statsRequested = true;

        cmd.RequestAsyncReadback(_statsBuffer, 6 * sizeof(uint), 0,
            (AsyncGPUReadbackRequest req) =>
            {
                _statsRequested = false;
                if (req.hasError || !req.done) return;

                var data = req.GetData<uint>();
                LastStats = new Stats
                {
                    inserts   = data[0],
                    evictions = data[1],
                    misses    = data[2],
                    decays    = data[3],
                    probes    = data[4],
                    lookups   = data[5],
                };

                AutoTuneDecay();
            });
    }

    void AutoTuneDecay()
    {
        if (Cfg.decayPeriod <= 0) return;

        // PI controller on smoothed load pressure.
        // One-sided: speeds up under load, never slows past user ceiling.
        float pressure = LastStats.LoadPressure;
        _smoothedPressure = Mathf.Lerp(_smoothedPressure, pressure, 0.1f);

        const float kP = 0.5f;
        const float targetPressure = 0.05f;
        float error = _smoothedPressure - targetPressure;

        if (error > 0f)
        {
            // Under pressure: decrease period (faster decay).
            int adjustment = Mathf.CeilToInt(error * kP * Cfg.decayPeriod);
            _effectiveDecayPeriod = Mathf.Max(
                _effectiveDecayPeriod - adjustment, 1);
        }
        else
        {
            // Relaxed: restore toward user setting (never exceed it).
            _effectiveDecayPeriod = Mathf.Min(
                _effectiveDecayPeriod + 1, Cfg.decayPeriod);
        }
    }

    // ─── Utility ────────────────────────────────────────────────

    int MustFindKernel(string name)
    {
        int k = _cs.FindKernel(name);
        if (k < 0)
            throw new InvalidOperationException(
                $"Kernel '{name}' not found in {_cs.name}. " +
                "Ensure VisibilityCache.compute is correct.");
        return k;
    }

    static int CeilDiv(int a, int b) => (a + b - 1) / b;
}
