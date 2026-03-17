"""Shared VisCache pass default parameters used by all graph scripts."""

VISCACHE_DEFAULTS = {
    "tableCapacity":   1 << 22,   # 4M entries = 32 MB
    "bootThreshold":   32,
    "varThreshold":    0.10,
    "pMin":            0.05,
    "fireflyBudget":   0.05,
    "decayPeriod":     300,       # auto-tuned by PI controller
    "decayPeriodMax":  600,
    "numLevels":       3,
    "cellCoarse":      10.0,
    "cellFine":        0.16,
    "enableVisCacheVisibilityCheck":   True,
    "enableVisCacheLightSelection": True,
    "enableVisCacheWarpReduction":  True,
    "enableVisCacheVarianceGate":   True,
    "enableVisCacheDecay":          True,
    "enableVisCachePressureEvict":  True,
}
