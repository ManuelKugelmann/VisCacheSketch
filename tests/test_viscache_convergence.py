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
TABLE_CAP   = 1 << 14   # 16K entries for test (full: 4M)
BOOT_THR    = 32
VAR_THR     = 0.10
MAX_PROBE   = 8
OVERFLOW_TH = 0xE000
P_MIN       = 0.05
FIREFLY_BDG = 0.05
K_MU_MIN    = 0.05
K_FOOT_MIN  = 4.0
K_FOOT_MAX  = 64.0

CELL_A = [10.0, 1.25, 0.08]
CELL_B = [10.0, 2.50, 0.62]

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

def vhf_addr(qa, qb, lvl):
    h = pcg3d(qa[0] ^ qb[0], qa[1] ^ qb[1], (qa[2] ^ qb[2]) + lvl * 0x9e3779b9)
    return (h[0] ^ h[1] ^ h[2]) & (TABLE_CAP - 1)

def vhf_fp(qa, qb, lvl):
    h = pcg3d((qa[0] ^ qb[0]) + 7, (qa[1] ^ qb[1]) + 13, (qa[2] ^ qb[2]) + lvl * 0xdeadbeef)
    return (h[0] ^ h[1] ^ h[2]) & 0xFFFFFFFF

def find_slot(table, addr0, fp, allow_insert):
    h2 = fp | 1
    for i in range(MAX_PROBE):
        slot = (addr0 + i * h2) & (TABLE_CAP - 1)
        efp, packed = table[slot]
        if efp == fp:
            return slot
        if allow_insert:
            if efp == 0 and packed == 0:
                return slot
            if i >= 2:
                total = packed & 0xFFFF
                threshold = 4 << (i - 2)
                if total < threshold:
                    return slot
    return -1

def insert(table, posA, posB, V, lvl=0):
    qa = jitter_quantize(posA, CELL_A[lvl], 0xAA ^ lvl)
    qb = jitter_quantize(posB, CELL_B[lvl], 0xBB ^ lvl)
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
    if (packed & 0xFFFF) > OVERFLOW_TH:
        sub = ((packed >> 16) >> 3) << 16 | ((packed & 0xFFFF) >> 3)
        packed = (packed - sub) & 0xFFFFFFFF
    table[slot] = (fp, packed)
    return True

def lookup(table, posA, posB, lvl=0):
    qa = jitter_quantize(posA, CELL_A[lvl], 0xAA ^ lvl)
    qb = jitter_quantize(posB, CELL_B[lvl], 0xBB ^ lvl)
    fp   = vhf_fp(qa, qb, lvl)
    addr = vhf_addr(qa, qb, lvl)
    slot = find_slot(table, addr, fp, allow_insert=False)
    if slot < 0:
        return None, None
    _, packed = table[slot]
    total = packed & 0xFFFF
    if total < BOOT_THR:
        return None, None
    vis = packed >> 16
    mu  = vis / total
    return mu, mu * (1.0 - mu)

def distance_gated_lod(d):
    """Mirror of VisCache.slang LOD selection."""
    lo = max(0, min(2, int(math.floor(math.log2(max(d, 1e-6) / K_FOOT_MAX)))))
    hi = max(0, min(2, int(math.floor(math.log2(max(d, 1e-6) / K_FOOT_MIN)))))
    return lo, hi

def background_decay(table, frame, decay_period):
    """Mirror of VisCacheDecay.cs.slang stride-based sweep."""
    stride = TABLE_CAP // decay_period
    offset = (frame % decay_period) * stride
    cleared = 0
    for i in range(stride):
        idx = offset + i
        if idx >= TABLE_CAP:
            break
        fp, packed = table[idx]
        if packed == 0:
            continue
        vis   = packed >> 16
        total = packed & 0xFFFF
        vis   = vis >> 1
        total = total >> 1
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

    table = [(0, 0)] * TABLE_CAP
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

    table = [(0, 0)] * TABLE_CAP
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
    table = [(0, 0)] * TABLE_CAP
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
    table = [(0, 0)] * TABLE_CAP
    posA  = (2.0, 3.0, 4.0)
    posB  = (20.0, 3.0, 4.0)

    for i in range(BOOT_THR - 1):
        insert(table, posA, posB, 1.0)
        mu, _ = lookup(table, posA, posB)
        assert mu is None, f"FAIL: returned result before boot threshold at sample {i+1}"

    insert(table, posA, posB, 1.0)
    mu, _ = lookup(table, posA, posB)
    assert mu is not None, "FAIL: still None at boot threshold"
    print(f"  PASS: None for {BOOT_THR-1} samples, valid at {BOOT_THR}")

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
        p    = max(var / VAR_THR, P_MIN)
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
    # For a power-of-two table, step=fp|1 (odd) is coprime with TABLE_CAP,
    # so iterating TABLE_CAP steps must visit every slot exactly once.
    N_TRIALS = 100
    for trial in range(N_TRIALS):
        fp = pcg(trial * 12345) & 0xFFFFFFFF
        step = fp | 1
        addr0 = pcg(trial * 67890) & (TABLE_CAP - 1)

        visited = set()
        pos = addr0
        for _ in range(TABLE_CAP):
            visited.add(pos)
            pos = (pos + step) & (TABLE_CAP - 1)

        assert len(visited) == TABLE_CAP, (
            f"FAIL: trial {trial}: visited {len(visited)}/{TABLE_CAP} slots "
            f"(step={step:#x})"
        )

    print(f"  PASS: all {N_TRIALS} trials visit every slot ({TABLE_CAP} entries)")

# ---------------------------------------------------------------------------
# Test 8: Pressure-scaled eviction respects graduated thresholds
# ---------------------------------------------------------------------------
def test_pressure_eviction():
    print("Test 8: Pressure-scaled eviction thresholds")
    # Fill slots at addr0 with entries of known total counts, then verify
    # that find_slot evicts weaker entries at deeper probe depths.

    table = [(0, 0)] * TABLE_CAP

    # Use a fixed fingerprint/addr for controlled testing
    test_fp   = 0xDEAD0001
    test_addr = 100

    # Pre-fill probe steps 0..7 with distinct fingerprints and known totals
    step = test_fp | 1
    for i in range(MAX_PROBE):
        slot = (test_addr + i * step) & (TABLE_CAP - 1)
        fake_fp = 0xBEEF0000 + i
        total = 3 if i < 4 else 20  # steps 0-3: low total; steps 4-7: high
        packed = total  # vis=0, total=total
        table[slot] = (fake_fp, packed)

    # Steps 0-1 are protected (never evicted)
    # Step 2: threshold=4, total=3 < 4 → should be evictable
    # Step 3: threshold=8, total=3 < 8 → should be evictable
    # find_slot should return step 2 (first evictable)
    slot = find_slot(table, test_addr, test_fp, allow_insert=True)
    expected_slot = (test_addr + 2 * step) & (TABLE_CAP - 1)
    assert slot == expected_slot, (
        f"FAIL: expected eviction at probe step 2 (slot {expected_slot}), "
        f"got slot {slot}"
    )

    # Now set step 2's total above threshold so it's protected
    table[expected_slot] = (0xBEEF0002, 5)  # total=5 >= threshold=4
    slot = find_slot(table, test_addr, test_fp, allow_insert=True)
    expected_slot_3 = (test_addr + 3 * step) & (TABLE_CAP - 1)
    assert slot == expected_slot_3, (
        f"FAIL: expected eviction at probe step 3 (slot {expected_slot_3}), "
        f"got slot {slot}"
    )
    print(f"  PASS: eviction respects graduated thresholds at probe depth 2+")

# ---------------------------------------------------------------------------
# Test 9: Multi-level LOD independence
# ---------------------------------------------------------------------------
def test_multilevel_independence():
    print("Test 9: Multi-level LOD independence")
    table = [(0, 0)] * TABLE_CAP
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
# Test 10: Distance-gated LOD selection
# ---------------------------------------------------------------------------
def test_distance_gated_lod():
    print("Test 10: Distance-gated LOD selection")
    # Very close → fine levels available
    lo, hi = distance_gated_lod(1.0)
    assert lo == 0, f"FAIL: d=1.0 expected lo=0 got {lo}"
    # At d=1.0: log2(1/64)=-6 → clamp 0, log2(1/4)=-2 → clamp 0
    # Both clamp to 0 at very short range

    # Medium distance → should include level 1
    lo, hi = distance_gated_lod(16.0)
    # log2(16/64)=log2(0.25)=-2 → clamp 0
    # log2(16/4)=log2(4)=2 → clamp 2
    assert lo == 0, f"FAIL: d=16 expected lo=0 got {lo}"
    assert hi == 2, f"FAIL: d=16 expected hi=2 got {hi}"

    # Far distance → coarse only
    lo, hi = distance_gated_lod(256.0)
    # log2(256/64)=2, log2(256/4)=6→clamp 2
    assert lo == 2, f"FAIL: d=256 expected lo=2 got {lo}"
    assert hi == 2, f"FAIL: d=256 expected hi=2 got {hi}"

    print(f"  PASS: LOD bounds correct for d=1, 16, 256")

# ---------------------------------------------------------------------------
# Test 11: Firefly-suppressed RR clamps high-contribution traces
# ---------------------------------------------------------------------------
def test_firefly_suppression():
    print("Test 11: Firefly-suppressed RR")
    MU_CACHE = 0.50
    var = MU_CACHE * (1.0 - MU_CACHE)  # 0.25

    # Low-contribution case: p is driven by variance
    contrib_low = 0.01
    p_floor_low = max(min(contrib_low / FIREFLY_BDG, 1.0), P_MIN)
    p_low = max(min(var / VAR_THR, 1.0), p_floor_low)
    assert p_low == 1.0, f"FAIL: low contrib should have p=1.0 (var=0.25 >> thr), got {p_low}"

    # High-contribution case: pFloor dominates over pMin
    contrib_high = 5.0  # very bright
    p_floor_high = max(min(contrib_high / FIREFLY_BDG, 1.0), P_MIN)
    assert p_floor_high == 1.0, f"FAIL: extreme contrib should clamp pFloor to 1.0"

    # Medium contribution where firefly floor > pMin but < 1
    contrib_med = 0.002
    p_floor_med = max(min(contrib_med / FIREFLY_BDG, 1.0), P_MIN)
    assert p_floor_med == P_MIN, f"FAIL: tiny contrib should use pMin={P_MIN}, got {p_floor_med}"

    # With low variance (converged), p would be low — but firefly floor raises it
    var_low = 0.001
    contrib_raise = 0.04  # pFloor = 0.04/0.05 = 0.8
    p_floor_raise = max(min(contrib_raise / FIREFLY_BDG, 1.0), P_MIN)
    p_final = max(min(var_low / VAR_THR, 1.0), p_floor_raise)
    assert p_final == p_floor_raise, (
        f"FAIL: firefly floor should raise p from {var_low/VAR_THR:.3f} to "
        f"{p_floor_raise:.3f}, got {p_final:.3f}"
    )

    # Verify unbiasedness under firefly suppression (statistical)
    GT = 0.30
    MU = 0.30
    N = 5000
    estimates = []
    for _ in range(N):
        var_s = MU * (1.0 - MU)
        p_var = max(min(var_s / VAR_THR, 1.0), P_MIN)
        c = 0.8  # moderate luminance contribution
        p_ff = max(min(c * max(MU, 1.0 - MU) / FIREFLY_BDG, 1.0), P_MIN)
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
    table = [(0, 0)] * TABLE_CAP
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
    # Entry should either be cleared or have total < BOOT_THR
    assert mu_after is None, "FAIL: entry should be cleared after many decay sweeps"
    print(f"  PASS: stale entry cleared after decay sweeps (was mu={mu_before:.2f})")


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
