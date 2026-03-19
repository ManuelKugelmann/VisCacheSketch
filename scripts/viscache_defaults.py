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
    # cellCoarse/cellFine omitted — auto-tuned from scene bounds (L0 ≈ sceneDiameter/10)
    "enableVisCacheVisibilityCheck":   True,
    "enableVisCacheLightSelection": True,
    "enableVisCacheWarpReduction":  True,
    "enableVisCacheVarianceGate":   True,
    "enableVisCacheDecay":          True,
    "enableVisCachePressureEvict":  True,
    "enableVisCacheJitter":         True,
    "enableVisCacheDirDistAddr":    False,
    "enableVisCacheAsymmetricAddr": False,
    "addrBScale":                   45.0,   # angular cell size in degrees (dirdist mode)
    "addrBDistScale":                8.0,    # distance cell size multiplier on cellCoarse
    "enableDiagnostics":            True,
}
