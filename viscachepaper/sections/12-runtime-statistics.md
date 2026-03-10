# 12. Runtime Statistics

Five per-frame atomic counters (inserts, evictions, misses, decay triggers, probe steps) on a dedicated buffer enable load monitoring at negligible cost. Derived metrics: load pressure (eviction/insert ratio), cache effectiveness (1 − miss/query), average probe depth. DECAY_PERIOD auto-tunes via PI controller on smoothed load pressure — one-sided: speeds up under load, never slows beyond a user-set ceiling (DECAY_PERIOD_MAX, the minimum responsiveness for the scene type). Quality knobs (TAU_RR, Pmin, firefly_budget) are never auto-tuned — they are user decisions.
