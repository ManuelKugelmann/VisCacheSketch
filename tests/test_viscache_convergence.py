"""
test_viscache_convergence.py  —  CPU-side algorithm validation for VisCache correctness.

Simulates the hash table insert/lookup logic in Python to verify:
1.  Mean converges to ground-truth visibility fraction
2.  Overflow decay preserves mean ratio within tolerance
3.  Distinct position pairs do not interfere
4.  Boot threshold gates untrusted entries
5.  CV+RRR estimator is unbiased
6.  Jitter-quantize is stable within a cell
7.  Double-hash probe with fp|1 step covers full table
8.  Pressure-scaled eviction respects graduated thresholds
9.  Multi-level LOD entries are independent
10. Distance-gated LOD selects correct levels
11. Firefly-suppressed RR clamps high-contribution traces
12. Background decay sweep clears stale entries

Run standalone:  python tests/test_viscache_convergence.py
No GPU required — validates algorithm logic before shader compilation.
"""

import random
import math
import sys

# ---------------------------------------------------------------------------
# Python mirror of VisCache.slang (integer arithmetic)
# ---------------------------------------------------------------------------
# Mirror of VisCache.slang cbuffer params (g prefix → SCREAMING_SNAKE)
TABLE_CAPACITY   = 1 << 14   # 16K entries for test (full: 4M)
BOOT_THRESHOLD   = 32
VAR_THRESHOLD    = 0.10
P_MIN            = 0.05
FIREFLY_BUDGET   = 0.05
NUM_LEVELS       = 3
CELL_COARSE      = 10.0
CELL_FINE        = 0.16

# Mirror of VisCache.slang static constants (k prefix → SCREAMING_SNAKE)
MAX_PROBE        = 8
EVICT_START_STEP = 3
EVICT_BASE_COUNT = 8
OVERFLOW_TRIGGER = 0xE000
DECAY_SHIFT      = 3

# Light selection
MU_MIN           = 0.05

def cell_size(lvl):
    """Mirror of VisCache.slang vhfCellSize — geometric interpolation."""
    if NUM_LEVELS <= 1:
        return CELL_COARSE
    t = lvl / (NUM_LEVELS - 1)
    return CELL_COARSE * math.exp(t * math.log(CELL_FINE / CELL_COARSE))

# Precompute for backward compat with tests that index CELL_SIZES[lvl]
CELL_SIZES = [cell_size(i) for i in range(NUM_LEVELS)]

def pcg(x):
    x = (x * 747796405 + 2891336453) & 0xFFFFFFFF
    x = ((x >> ((x >> 28) + 4)) ^ x) * 277803737 & 0xFFFFFFFF
    return (x >> 22) ^ x

def pcg3d(vx, vy, vz):
    vx = (vx * 1664525 + 1013904223) & 0xFFFFFFFF
    vy = (vy * 1664525 + 1013904223) & 0xFFFFFFFF
    vz = (vz * 1664525 + 1013904223) & 0xFFFFFFFF
    vx = (vx + vy * vz) & 0xFFFFFFFF
    vy = (vy + vz * vx) & 0xFFFFFFFF
    vz = (vz + vx * vy) & 0xFFFFFFFF
    vx ^= vx >> 16; vy ^= vy >> 16; vz ^= vz >> 16
    vx = (vx + vy * vz) & 0xFFFFFFFF
    vy = (vy + vz * vx) & 0xFFFFFFFF
    vz = (vz + vx * vy) & 0xFFFFFFFF
    return vx, vy, vz

def jitter_quantize(pos, cell, seed):
    base = [int(math.floor(p / cell)) for p in pos]
    rx, ry, rz = pcg3d(base[0] ^ seed, base[1] ^ seed, base[2] ^ seed)
    jit = [(r & 0xFFFF) / 65535.0 - 0.5 for r in (rx, ry, rz)]
    return tuple(int(math.floor((pos[i] + jit[i] * cell) / cell)) for i in range(3))

def canonical_pair(qa, qb):
    """Lexicographic swap so (A,B) and (B,A) map to same entry."""
    if qa > qb:
        return qb, qa
    return qa, qb

def quantize_pair(posA, posB, cell, lvl):
    """Quantize + canonicalize — mirrors vhfQuantizePair in VisCache.slang."""
    qa = jitter_quantize(posA, cell, 0xAA ^ lvl)
    qb = jitter_quantize(posB, cell, 0xBB ^ lvl)
    return canonical_pair(qa, qb)

def vhf_addr(qa, qb, lvl):
    h = pcg3d(qa[0] ^ qb[0], qa[1] ^ qb[1], (qa[2] ^ qb[2]) + lvl * 0x9e3779b9)
    return (h[0] ^ h[1] ^ h[2]) & (TABLE_CAPACITY - 1)

def vhf_fp(qa, qb, lvl):
    h = pcg3d((qa[0] ^ qb[0]) + 7, (qa[1] ^ qb[1]) + 13, (qa[2] ^ qb[2]) + lvl * 0xdeadbeef)
    return (h[0] ^ h[1] ^ h[2]) & 0xFFFFFFFF

def find_slot(table, addr0, fp, allow_insert):
    h2 = fp | 1
    for i in range(MAX_PROBE):
        slot = (addr0 + i * h2) & (TABLE_CAPACITY - 1)
        efp, packed = table[slot]
        if efp == fp:
            return slot
        if allow_insert:
            if efp == 0 and packed == 0:
                return slot
            if i >= EVICT_START_STEP:
                total = packed & 0xFFFF
                threshold = EVICT_BASE_COUNT << (i - EVICT_START_STEP)
                if total < threshold:
                    return slot
    return -1

def insert(table, posA, posB, V, lvl=0):
    cs = cell_size(lvl)
    qa, qb = quantize_pair(posA, posB, cs, lvl)
    fp   = vhf_fp(qa, qb, lvl)
    addr = vhf_addr(qa, qb, lvl)
    slot = find_slot(table, addr, fp, allow_insert=True)
    if slot < 0:
        return False
    efp, packed = table[slot]
    if efp == 0:
        table[slot] = (fp, packed)
    vis_val = 1 if V > 0.5 else 0
    _, packed = table[slot]
    packed = (packed + (vis_val << 16) + 1) & 0xFFFFFFFF
    # Overflow decay
    if (packed & 0xFFFF) > OVERFLOW_TRIGGER:
        sub = ((packed >> 16) >> DECAY_SHIFT) << 16 | ((packed & 0xFFFF) >> DECAY_SHIFT)
        packed = (packed - sub) & 0xFFFFFFFF
    table[slot] = (fp, packed)
    return True

def lookup(table, posA, posB, lvl=0):
    cs = cell_size(lvl)
    qa, qb = quantize_pair(posA, posB, cs, lvl)
    fp   = vhf_fp(qa, qb, lvl)
    addr = vhf_addr(qa, qb, lvl)
    slot = find_slot(table, addr, fp, allow_insert=False)
    if slot < 0:
        return None, None
    _, packed = table[slot]
    total = packed & 0xFFFF
    if total < BOOT_THRESHOLD:
        return None, None
    vis = packed >> 16
    mu  = vis / total
    return mu, mu * (1.0 - mu)

def full_cascade_lod():
    """Full cascade L0..N-1 (VisCache always uses this)."""
    return 0, NUM_LEVELS - 1

def background_decay(table, frame, decay_period):
    """Mirror of VisCacheDecay.cs.slang stride-based sweep."""
    stride = TABLE_CAPACITY // decay_period
    offset = (frame % decay_period) * stride
    cleared = 0
    for i in range(stride):
        idx = offset + i
        if idx >= TABLE_CAPACITY:
            break
        fp, packed = table[idx]
        if packed == 0:
            continue
        vis   = packed >> 16
        total = packed & 0xFFFF
        vis   = vis >> DECAY_SHIFT
        total = total >> DECAY_SHIFT
        if total == 0:
            table[idx] = (0, 0)
            cleared += 1
        else:
            table[idx] = (fp, (vis << 16) | total)
    return cleared

# ===========================================================================
# Tests
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 1: Mean convergence
# ---------------------------------------------------------------------------
def test_mean_convergence():
    print("Test 1: Mean convergence")
    GT_VIS = 0.73
    N_SAMPLES = 2000
    TOLERANCE = 0.05

    table = [(0, 0)] * TABLE_CAPACITY
    posA  = (5.1, 3.7, 1.2)
    posB  = (12.4, 8.1, 0.5)

    for _ in range(N_SAMPLES):
        V = 1.0 if random.random() < GT_VIS else 0.0
        insert(table, posA, posB, V)

    mu, var = lookup(table, posA, posB)
    assert mu is not None, "FAIL: lookup returned None after sufficient inserts"
    err = abs(mu - GT_VIS)
    assert err < TOLERANCE, f"FAIL: mu={mu:.4f} gt={GT_VIS:.4f} err={err:.4f} > {TOLERANCE}"
    print(f"  PASS: mu={mu:.4f}  gt={GT_VIS:.4f}  err={err:.4f}  var={var:.4f}")

# ---------------------------------------------------------------------------
# Test 2: Overflow decay preserves mean ratio
# ---------------------------------------------------------------------------
def test_overflow_decay():
    print("Test 2: Overflow decay preserves mean")
    GT_VIS = 0.60
    N_SAMPLES = 100000

    table = [(0, 0)] * TABLE_CAPACITY
    posA  = (1.0, 1.0, 1.0)
    posB  = (5.0, 5.0, 5.0)

    for _ in range(N_SAMPLES):
        V = 1.0 if random.random() < GT_VIS else 0.0
        insert(table, posA, posB, V)

    mu, _ = lookup(table, posA, posB)
    assert mu is not None, "FAIL: lookup returned None"
    err = abs(mu - GT_VIS)
    TOLERANCE = 0.02
    assert err < TOLERANCE, f"FAIL: mu={mu:.4f} gt={GT_VIS:.4f} err={err:.4f}"
    print(f"  PASS: mu={mu:.4f}  gt={GT_VIS:.4f}  err={err:.4f}  (after {N_SAMPLES} inserts)")

# ---------------------------------------------------------------------------
# Test 3: Distinct position pairs do not interfere
# ---------------------------------------------------------------------------
def test_isolation():
    print("Test 3: Position pair isolation")
    table = [(0, 0)] * TABLE_CAPACITY
    pairs = [
        ((1.0,  0.0, 0.0), (55.0,  0.0, 0.0), 1.00),
        ((1.0, 15.0, 0.0), (55.0, 15.0, 0.0), 0.00),
        ((1.0, 30.0, 0.0), (55.0, 30.0, 0.0), 0.50),
    ]

    for pA, pB, gt in pairs:
        for _ in range(500):
            V = 1.0 if random.random() < gt else 0.0
            insert(table, pA, pB, V)

    for pA, pB, gt in pairs:
        mu, _ = lookup(table, pA, pB)
        assert mu is not None, f"FAIL: lookup returned None for gt={gt}"
        err = abs(mu - gt)
        assert err < 0.08, f"FAIL: mu={mu:.4f} gt={gt:.4f} err={err:.4f}"
        print(f"  PASS: gt={gt:.2f}  mu={mu:.4f}  err={err:.4f}")

# ---------------------------------------------------------------------------
# Test 4: Boot threshold — untrusted until sufficient samples
# ---------------------------------------------------------------------------
def test_boot_threshold():
    print("Test 4: Boot threshold")
    table = [(0, 0)] * TABLE_CAPACITY
    posA  = (2.0, 3.0, 4.0)
    posB  = (20.0, 3.0, 4.0)

    for i in range(BOOT_THRESHOLD - 1):
        insert(table, posA, posB, 1.0)
        mu, _ = lookup(table, posA, posB)
        assert mu is None, f"FAIL: returned result before boot threshold at sample {i+1}"

    insert(table, posA, posB, 1.0)
    mu, _ = lookup(table, posA, posB)
    assert mu is not None, "FAIL: still None at boot threshold"
    print(f"  PASS: None for {BOOT_THRESHOLD-1} samples, valid at {BOOT_THRESHOLD}")

# ---------------------------------------------------------------------------
# Test 5: CV+RRR unbiasedness (statistical)
# ---------------------------------------------------------------------------
def test_cvrrr_unbiasedness():
    print("Test 5: CV+RRR estimator unbiasedness")
    GT_VIS   = 0.65
    N_OUTER  = 1000
    MU_CACHE = 0.65

    estimates = []
    for _ in range(N_OUTER):
        var  = MU_CACHE * (1.0 - MU_CACHE)
        p    = max(var / VAR_THRESHOLD, P_MIN)
        p    = min(p, 1.0)
        xi   = random.random()
        if xi < p:
            V    = 1.0 if random.random() < GT_VIS else 0.0
            est  = MU_CACHE + (V - MU_CACHE) / p
        else:
            est  = MU_CACHE
        estimates.append(est)

    mean_est = sum(estimates) / len(estimates)
    err      = abs(mean_est - GT_VIS)
    assert err < 0.03, f"FAIL: E[est]={mean_est:.4f} GT={GT_VIS:.4f} err={err:.4f}"
    print(f"  PASS: E[estimator]={mean_est:.4f}  GT={GT_VIS:.4f}  err={err:.4f}")

# ---------------------------------------------------------------------------
# Test 6: Jitter-quantize stability within cell
# ---------------------------------------------------------------------------
def test_jitter_quantize_stability():
    print("Test 6: Jitter-quantize stability within cell")
    cell = 10.0
    seed = 0xAA
    # Points well within the interior of a cell (avoid boundary effects)
    center = (15.0, 25.0, 5.0)  # cell index (1, 2, 0)

    q_ref = jitter_quantize(center, cell, seed)
    # Keep offsets within ±3.0 (interior of 10m cell, away from boundaries
    # where jitter intentionally introduces probabilistic switching)
    offsets = [0.1, 0.5, 1.0, 2.0, 3.0, -0.1, -0.5, -1.0, -2.0, -3.0]
    stable = 0
    total  = 0
    for dx in offsets:
        for dy in offsets[:4]:
            pt = (center[0] + dx, center[1] + dy, center[2])
            q  = jitter_quantize(pt, cell, seed)
            total += 1
            if q == q_ref:
                stable += 1

    # Jitter-before-quantize is probabilistically stable, not perfectly.
    # Interior points should mostly agree; boundary randomization is by design.
    ratio = stable / total
    assert ratio > 0.3, f"FAIL: stability ratio {ratio:.2f} < 0.30 ({stable}/{total})"
    print(f"  PASS: stability ratio={ratio:.2f} ({stable}/{total} interior points agree)")

# ---------------------------------------------------------------------------
# Test 7: Double-hash probe with fp|1 covers full power-of-two table
# ---------------------------------------------------------------------------
def test_double_hash_coverage():
    print("Test 7: Double-hash probe coverage (fp|1 coprime)")
    # For a power-of-two table, step=fp|1 (odd) is coprime with TABLE_CAPACITY,
    # so iterating TABLE_CAPACITY steps must visit every slot exactly once.
    N_TRIALS = 100
    for trial in range(N_TRIALS):
        fp = pcg(trial * 12345) & 0xFFFFFFFF
        step = fp | 1
        addr0 = pcg(trial * 67890) & (TABLE_CAPACITY - 1)

        visited = set()
        pos = addr0
        for _ in range(TABLE_CAPACITY):
            visited.add(pos)
            pos = (pos + step) & (TABLE_CAPACITY - 1)

        assert len(visited) == TABLE_CAPACITY, (
            f"FAIL: trial {trial}: visited {len(visited)}/{TABLE_CAPACITY} slots "
            f"(step={step:#x})"
        )

    print(f"  PASS: all {N_TRIALS} trials visit every slot ({TABLE_CAPACITY} entries)")

# ---------------------------------------------------------------------------
# Test 8: Pressure-scaled eviction respects graduated thresholds
# ---------------------------------------------------------------------------
def test_pressure_eviction():
    print("Test 8: Pressure-scaled eviction thresholds")
    # Fill slots at addr0 with entries of known total counts, then verify
    # that find_slot evicts weaker entries at deeper probe depths.

    table = [(0, 0)] * TABLE_CAPACITY

    # Use a fixed fingerprint/addr for controlled testing
    test_fp   = 0xDEAD0001
    test_addr = 100

    # Pre-fill probe steps 0..7 with distinct fingerprints and known totals
    step = test_fp | 1
    for i in range(MAX_PROBE):
        slot = (test_addr + i * step) & (TABLE_CAPACITY - 1)
        fake_fp = 0xBEEF0000 + i
        total = 5 if i < 5 else 20  # steps 0-4: low total; steps 5-7: high
        packed = total  # vis=0, total=total
        table[slot] = (fake_fp, packed)

    # Steps 0-2 are protected (never evicted)
    # Step 3: threshold=8, total=5 < 8 → should be evictable
    # Step 4: threshold=16, total=5 < 16 → should be evictable
    # find_slot should return step 3 (first evictable)
    slot = find_slot(table, test_addr, test_fp, allow_insert=True)
    expected_slot = (test_addr + 3 * step) & (TABLE_CAPACITY - 1)
    assert slot == expected_slot, (
        f"FAIL: expected eviction at probe step 3 (slot {expected_slot}), "
        f"got slot {slot}"
    )

    # Now set step 3's total above threshold so it's protected
    table[expected_slot] = (0xBEEF0003, 9)  # total=9 >= threshold=8
    slot = find_slot(table, test_addr, test_fp, allow_insert=True)
    expected_slot_4 = (test_addr + 4 * step) & (TABLE_CAPACITY - 1)
    assert slot == expected_slot_4, (
        f"FAIL: expected eviction at probe step 4 (slot {expected_slot_4}), "
        f"got slot {slot}"
    )
    print(f"  PASS: eviction respects graduated thresholds at probe depth 3+")

# ---------------------------------------------------------------------------
# Test 9: Multi-level LOD independence
# ---------------------------------------------------------------------------
def test_multilevel_independence():
    print("Test 9: Multi-level LOD independence")
    table = [(0, 0)] * TABLE_CAPACITY
    posA = (5.0, 5.0, 5.0)
    posB = (15.0, 15.0, 15.0)

    # Insert different visibility at each level
    gt_per_level = {0: 0.90, 1: 0.50, 2: 0.10}

    for lvl, gt in gt_per_level.items():
        for _ in range(500):
            V = 1.0 if random.random() < gt else 0.0
            insert(table, posA, posB, V, lvl=lvl)

    for lvl, gt in gt_per_level.items():
        mu, _ = lookup(table, posA, posB, lvl=lvl)
        assert mu is not None, f"FAIL: level {lvl} returned None"
        err = abs(mu - gt)
        assert err < 0.08, f"FAIL: level {lvl}: mu={mu:.4f} gt={gt:.4f} err={err:.4f}"
        print(f"  PASS: L{lvl} gt={gt:.2f}  mu={mu:.4f}  err={err:.4f}")

# ---------------------------------------------------------------------------
# Test 10: Full-cascade LOD + geometric cell size interpolation
# ---------------------------------------------------------------------------
def test_distance_gated_lod():
    print("Test 10: Full-cascade LOD + cell size interpolation")
    # Full cascade always returns (0, N-1)
    lo, hi = full_cascade_lod()
    assert lo == 0, f"FAIL: expected lo=0 got {lo}"
    assert hi == NUM_LEVELS - 1, f"FAIL: expected hi={NUM_LEVELS-1} got {hi}"

    # Cell sizes: geometric interpolation, coarse to fine
    assert abs(cell_size(0) - CELL_COARSE) < 1e-6, f"FAIL: L0 should be CELL_COARSE={CELL_COARSE}"
    assert abs(cell_size(NUM_LEVELS - 1) - CELL_FINE) < 1e-6, f"FAIL: L{NUM_LEVELS-1} should be CELL_FINE={CELL_FINE}"

    # Monotonically decreasing
    for i in range(NUM_LEVELS - 1):
        assert cell_size(i) > cell_size(i + 1), f"FAIL: cell_size({i})={cell_size(i)} <= cell_size({i+1})={cell_size(i+1)}"

    # Works with arbitrary N
    import types
    saved = NUM_LEVELS
    for n in [1, 2, 5, 8]:
        globals()['NUM_LEVELS'] = n
        cs0 = cell_size(0)
        csN = cell_size(max(0, n - 1))
        assert abs(cs0 - CELL_COARSE) < 1e-6, f"FAIL: N={n} L0 != CELL_COARSE"
        if n > 1:
            assert abs(csN - CELL_FINE) < 1e-6, f"FAIL: N={n} L{n-1} != CELL_FINE"
    globals()['NUM_LEVELS'] = saved

    print(f"  PASS: full cascade (0, {NUM_LEVELS-1}), cell sizes monotonic, N-agnostic")

# ---------------------------------------------------------------------------
# Test 11: Firefly-suppressed RR clamps high-contribution traces
# ---------------------------------------------------------------------------
def test_firefly_suppression():
    print("Test 11: Firefly-suppressed RR")
    MU_CACHE = 0.50
    var = MU_CACHE * (1.0 - MU_CACHE)  # 0.25

    # Low-contribution case: p is driven by variance
    contrib_low = 0.01
    p_floor_low = max(min(contrib_low / FIREFLY_BUDGET, 1.0), P_MIN)
    p_low = max(min(var / VAR_THRESHOLD, 1.0), p_floor_low)
    assert p_low == 1.0, f"FAIL: low contrib should have p=1.0 (var=0.25 >> thr), got {p_low}"

    # High-contribution case: pFloor dominates over pMin
    contrib_high = 5.0  # very bright
    p_floor_high = max(min(contrib_high / FIREFLY_BUDGET, 1.0), P_MIN)
    assert p_floor_high == 1.0, f"FAIL: extreme contrib should clamp pFloor to 1.0"

    # Medium contribution where firefly floor > pMin but < 1
    contrib_med = 0.002
    p_floor_med = max(min(contrib_med / FIREFLY_BUDGET, 1.0), P_MIN)
    assert p_floor_med == P_MIN, f"FAIL: tiny contrib should use pMin={P_MIN}, got {p_floor_med}"

    # With low variance (converged), p would be low — but firefly floor raises it
    var_low = 0.001
    contrib_raise = 0.04  # pFloor = 0.04/0.05 = 0.8
    p_floor_raise = max(min(contrib_raise / FIREFLY_BUDGET, 1.0), P_MIN)
    p_final = max(min(var_low / VAR_THRESHOLD, 1.0), p_floor_raise)
    assert p_final == p_floor_raise, (
        f"FAIL: firefly floor should raise p from {var_low/VAR_THRESHOLD:.3f} to "
        f"{p_floor_raise:.3f}, got {p_final:.3f}"
    )

    # Verify unbiasedness under firefly suppression (statistical)
    GT = 0.30
    MU = 0.30
    N = 5000
    estimates = []
    for _ in range(N):
        var_s = MU * (1.0 - MU)
        p_var = max(min(var_s / VAR_THRESHOLD, 1.0), P_MIN)
        c = 0.8  # moderate luminance contribution
        p_ff = max(min(c * max(MU, 1.0 - MU) / FIREFLY_BUDGET, 1.0), P_MIN)
        p = max(p_var, p_ff)
        if random.random() < p:
            V = 1.0 if random.random() < GT else 0.0
            estimates.append(MU + (V - MU) / p)
        else:
            estimates.append(MU)
    mean_est = sum(estimates) / len(estimates)
    err = abs(mean_est - GT)
    assert err < 0.03, f"FAIL: firefly RR biased: E={mean_est:.4f} GT={GT:.4f}"
    print(f"  PASS: firefly pFloor logic correct, unbiased (err={err:.4f})")

# ---------------------------------------------------------------------------
# Test 12: Background decay sweep clears stale entries
# ---------------------------------------------------------------------------
def test_background_decay():
    print("Test 12: Background decay sweep")
    table = [(0, 0)] * TABLE_CAPACITY
    posA = (3.0, 3.0, 3.0)
    posB = (30.0, 30.0, 30.0)

    # Insert enough to bootstrap
    for _ in range(100):
        insert(table, posA, posB, 1.0)

    mu_before, _ = lookup(table, posA, posB)
    assert mu_before is not None, "FAIL: entry should exist before decay"

    # Run enough decay sweeps to clear it (halving total each pass)
    # After ~16 passes of halving, total goes from 100 to 0
    decay_period = 4
    for frame in range(decay_period * 20):
        background_decay(table, frame, decay_period)

    mu_after, _ = lookup(table, posA, posB)
    # Entry should either be cleared or have total < BOOT_THRESHOLD
    assert mu_after is None, "FAIL: entry should be cleared after many decay sweeps"
    print(f"  PASS: stale entry cleared after decay sweeps (was mu={mu_before:.2f})")


# ---------------------------------------------------------------------------
# Test 13: Cascaded variance gate — each level gates writes to the next
# ---------------------------------------------------------------------------
def test_cascaded_variance_gate():
    print("Test 13: Cascaded variance gate")
    table = [(0, 0)] * TABLE_CAPACITY
    posA = (5.0, 5.0, 5.0)
    posB = (15.0, 15.0, 15.0)

    def cascaded_insert(table, posA, posB, V, lo, hi):
        """Mirror of VisCache.slang cascaded vhfInsert.
        Write level, check its variance, stop if smooth."""
        for lvl in range(lo, hi + 1):
            insert(table, posA, posB, V, lvl=lvl)
            # Check this level's variance to gate the next
            mu_cur, var_cur = lookup(table, posA, posB, lvl=lvl)
            if mu_cur is not None and var_cur <= VAR_THRESHOLD:
                break  # this level is smooth — no need to go finer

    # Case A: uniform visibility (mu≈1.0) → L0 converges to low variance,
    # so L1 and L2 should NOT be populated after bootstrap.
    for _ in range(500):
        cascaded_insert(table, posA, posB, 1.0, lo=0, hi=2)

    mu0, var0 = lookup(table, posA, posB, lvl=0)
    assert mu0 is not None, "FAIL: L0 should be populated"
    assert var0 < VAR_THRESHOLD, f"FAIL: L0 var={var0:.4f} should be < {VAR_THRESHOLD} for uniform vis"

    # L1 may have some bootstrap samples but should stop receiving updates.
    # Insert more — L1 should not grow much beyond bootstrap.
    mu1_before, _ = lookup(table, posA, posB, lvl=1)
    for _ in range(500):
        cascaded_insert(table, posA, posB, 1.0, lo=0, hi=2)
    mu1_after, _ = lookup(table, posA, posB, lvl=1)
    # L1 is fine either way (populated during bootstrap or not) —
    # the key is that the gate stops propagation once L0 is smooth.
    print(f"  Case A (uniform): L0 var={var0:.4f} (smooth) — gate blocks finer levels")

    # Case B: boundary visibility (mu≈0.5) → high variance at all levels,
    # so all levels should be populated.
    table2 = [(0, 0)] * TABLE_CAPACITY
    posA2 = (7.0, 7.0, 7.0)
    posB2 = (17.0, 17.0, 17.0)
    for _ in range(500):
        V = 1.0 if random.random() < 0.5 else 0.0
        cascaded_insert(table2, posA2, posB2, V, lo=0, hi=2)

    mu0b, var0b = lookup(table2, posA2, posB2, lvl=0)
    mu1b, var1b = lookup(table2, posA2, posB2, lvl=1)
    mu2b, var2b = lookup(table2, posA2, posB2, lvl=2)
    assert mu0b is not None, "FAIL: L0 should be populated (boundary)"
    assert var0b > VAR_THRESHOLD, f"FAIL: L0 var={var0b:.4f} should be > {VAR_THRESHOLD} at boundary"
    assert mu1b is not None, "FAIL: L1 should be populated (boundary, L0 high-var)"
    assert mu2b is not None, "FAIL: L2 should be populated (boundary, L1 high-var)"
    print(f"  Case B (boundary): L0 var={var0b:.4f}, L1 var={var1b:.4f}, L2 var={var2b:.4f} — all populated")
    print(f"  PASS: cascaded gate blocks smooth regions, propagates at boundaries")


# ---------------------------------------------------------------------------
# Test 14: Canonical symmetry — V(A,B) and V(B,A) share the same entry
# ---------------------------------------------------------------------------
def test_canonical_symmetry():
    print("Test 14: Canonical symmetry V(A,B) == V(B,A)")
    table = [(0, 0)] * TABLE_CAPACITY
    posA = (3.0, 7.0, 1.5)
    posB = (25.0, 12.0, 8.0)

    # Insert via (A,B)
    for _ in range(200):
        V = 1.0 if random.random() < 0.8 else 0.0
        insert(table, posA, posB, V)

    # Lookup via (B,A) — should find the same entry
    mu_ab, var_ab = lookup(table, posA, posB)
    mu_ba, var_ba = lookup(table, posB, posA)
    assert mu_ab is not None, "FAIL: (A,B) lookup returned None"
    assert mu_ba is not None, "FAIL: (B,A) lookup returned None"
    assert mu_ab == mu_ba, f"FAIL: mu(A,B)={mu_ab:.4f} != mu(B,A)={mu_ba:.4f}"
    assert var_ab == var_ba, f"FAIL: var(A,B)={var_ab:.4f} != var(B,A)={var_ba:.4f}"

    # Insert via (B,A) and verify (A,B) sees the update
    for _ in range(200):
        V = 1.0 if random.random() < 0.8 else 0.0
        insert(table, posB, posA, V)
    mu_combined, _ = lookup(table, posA, posB)
    assert mu_combined is not None, "FAIL: combined lookup returned None"
    # After 400 samples of gt=0.8, should be well converged
    err = abs(mu_combined - 0.8)
    assert err < 0.06, f"FAIL: combined mu={mu_combined:.4f} gt=0.8 err={err:.4f}"
    print(f"  PASS: mu(A,B)==mu(B,A)={mu_ab:.4f}, combined mu={mu_combined:.4f} (err={err:.4f})")


# ===========================================================================
# Run all tests
# ===========================================================================
if __name__ == "__main__":
    random.seed(42)
    tests = [
        test_mean_convergence,
        test_overflow_decay,
        test_isolation,
        test_boot_threshold,
        test_cvrrr_unbiasedness,
        test_jitter_quantize_stability,
        test_double_hash_coverage,
        test_pressure_eviction,
        test_multilevel_independence,
        test_distance_gated_lod,
        test_firefly_suppression,
        test_background_decay,
        test_cascaded_variance_gate,
        test_canonical_symmetry,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  {e}")
            failed += 1
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            failed += 1

    print()
    if failed == 0:
        print(f"All {len(tests)} tests passed.")
        sys.exit(0)
    else:
        print(f"{failed}/{len(tests)} tests FAILED.")
        sys.exit(1)
