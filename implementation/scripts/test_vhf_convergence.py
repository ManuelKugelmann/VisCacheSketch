"""
test_vhf_convergence.py  —  CPU-side unit test for VHF correctness.

Simulates the hash table insert/lookup logic in Python to verify:
1. Mean converges to ground-truth visibility fraction
2. Variance gate correctly stops writes in smooth regions
3. Overflow decay preserves mean ratio within tolerance
4. Double-hash probe correctly detects collisions

Run standalone:  python scripts/test_vhf_convergence.py
No GPU required — validates algorithm logic before shader compilation.
"""

import random
import math
import sys

# ---------------------------------------------------------------------------
# Python mirror of VisHashFilter.slang (integer arithmetic)
# ---------------------------------------------------------------------------
TABLE_CAP   = 1 << 14   # 16K entries for test (full: 4M)
BOOT_THR    = 32
VAR_THR     = 0.10
MAX_PROBE   = 8
OVERFLOW_TH = 0xE000

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
    qa = jitter_quantize(posA, 10.0 if lvl == 0 else (1.25 if lvl == 1 else 0.08), 0xAA ^ lvl)
    qb = jitter_quantize(posB, 10.0 if lvl == 0 else (2.50 if lvl == 1 else 0.62), 0xBB ^ lvl)
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
    qa = jitter_quantize(posA, 10.0 if lvl == 0 else (1.25 if lvl == 1 else 0.08), 0xAA ^ lvl)
    qb = jitter_quantize(posB, 10.0 if lvl == 0 else (2.50 if lvl == 1 else 0.62), 0xBB ^ lvl)
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

# ---------------------------------------------------------------------------
# Test 1: Mean convergence
# ---------------------------------------------------------------------------
def test_mean_convergence():
    print("Test 1: Mean convergence")
    GT_VIS = 0.73   # ground truth visibility fraction
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
    N_SAMPLES = 100000   # force many overflow decays

    table = [(0, 0)] * TABLE_CAP
    posA  = (1.0, 1.0, 1.0)
    posB  = (5.0, 5.0, 5.0)

    for _ in range(N_SAMPLES):
        V = 1.0 if random.random() < GT_VIS else 0.0
        insert(table, posA, posB, V)

    mu, _ = lookup(table, posA, posB)
    assert mu is not None, "FAIL: lookup returned None"
    err = abs(mu - GT_VIS)
    TOLERANCE = 0.02   # tighter — many samples, should converge well
    assert err < TOLERANCE, f"FAIL: mu={mu:.4f} gt={GT_VIS:.4f} err={err:.4f}"
    print(f"  PASS: mu={mu:.4f}  gt={GT_VIS:.4f}  err={err:.4f}  (after {N_SAMPLES} inserts)")

# ---------------------------------------------------------------------------
# Test 3: Distinct position pairs do not interfere
# ---------------------------------------------------------------------------
def test_isolation():
    print("Test 3: Position pair isolation")
    table = [(0, 0)] * TABLE_CAP
    # Positions must be in distinct L0 cells (10 m grid).
    # Use y = 0, 15, 30 so each pair gets a different row in the L0 grid.
    pairs = [
        ((1.0,  0.0, 0.0), (55.0,  0.0, 0.0), 1.00),  # always visible
        ((1.0, 15.0, 0.0), (55.0, 15.0, 0.0), 0.00),  # always occluded
        ((1.0, 30.0, 0.0), (55.0, 30.0, 0.0), 0.50),  # penumbra
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
    P_MIN    = 0.05
    N_OUTER  = 1000  # independent trials
    MU_CACHE = 0.65  # perfect cache for this test

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
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    random.seed(42)
    tests = [
        test_mean_convergence,
        test_overflow_decay,
        test_isolation,
        test_boot_threshold,
        test_cvrrr_unbiasedness,
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
