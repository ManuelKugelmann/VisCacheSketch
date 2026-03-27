"""Shared VisCache pass default parameters used by all graph scripts."""

VISCACHE_DEFAULTS = {
    "tableCapacity":   1 << 22,   # 4M entries = 32 MB
    "bootThreshold":   32,
    "varThreshold":    0.10,
    "pMin":            0.05,
    "fireflyBudget":   0.05,
    "decayPeriod":     300,       # auto-tuned by PI controller
    "decayPeriodMax":  600,
    "numLevels":       8,
    # cellACoarse omitted — auto-tuned from scene bounds
    "cellBCoarse":      20.0,   # posB coarsest cell (world units)
    "angularBCoarse":   90.0,   # direction coarsest cell (degrees, dirdist mode)
    "distBCoarse":      10.0,   # distance coarsest cell (world units, dirdist mode)
    "normalBCoarse":    60.0,   # normal coarsest cell (degrees, 60°≈6 bins, 360°=collapsed)
    "enableVisCacheVisibilityCheck":   True,
    "enableVisCacheLightSelection": True,
    "enableVisCacheWarpReduction":  True,
    "enableVisCacheVarianceGate":   True,
    "enableVisCacheDecay":          True,
    "enableVisCachePressureEvict":  True,
    "enableVisCacheJitterA":        True,
    "enableVisCacheJitterB":        True,
    "enableVisCacheAdaptivePMin":   True,
    "enableVisCacheNormalAddr":     False,
    "enableVisCacheDirDistAddr":    False,
    "enableDiagnostics":            True,
}
