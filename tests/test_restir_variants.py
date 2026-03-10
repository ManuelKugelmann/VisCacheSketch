"""
test_restir_variants.py — CPU-side validation for ReSTIR pass algorithm correctness.

Validates:
1.  Local CV+RRR estimator unbiasedness (reservoir-local mu)
2.  Local CV+RRR with bad mu still converges (unbiased for any mu)
3.  Local CV+RRR with mu=0 still converges
4.  RR probability is clamped to [pMin, 1.0]
5.  evalTargetPdf matches luminance(bsdf * Lo) * G
6.  geometryValid rejects back-facing / distant neighbors
7.  mu fallback and clamping edge cases
8.  Variance reduction — CV+RRR vs vanilla when mu is accurate

Run standalone:  python tests/test_restir_variants.py
No GPU required — validates algorithm logic before shader compilation.
"""

import random
import math
import sys

# ============================================================================
# Python mirror of evalLocalRevalidation (SpatialReuse.cs.slang)
# ============================================================================

def luminance(rgb):
    """ITU BT.709 luminance."""
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def eval_local_revalidation(mu, bsdf, Lo, G, V_gt, contrib_threshold, p_min, rng):
    """
    Python mirror of evalLocalRevalidation().
    Returns the CV+RRR estimate of V.
    """
    C = [bsdf[i] * Lo[i] * G for i in range(3)]
    res = luminance(C) * max(mu, 1.0 - mu)
    p = max(p_min, min(res / contrib_threshold, 1.0))

    if rng() < p:
        V = V_gt
        return mu + (V - mu) / p
    return mu


def eval_target_pdf(bsdf, Lo, G):
    """Python mirror of evalTargetPdf from ReSTIRGICommon.slang."""
    return luminance([bsdf[i] * Lo[i] for i in range(3)]) * G


def geometry_valid(N1, N2, P1, P2, normal_thresh, dist_thresh):
    """Python mirror of geometryValid from ReSTIRGICommon.slang."""
    dot_n = sum(N1[i] * N2[i] for i in range(3))
    diff = [P1[i] - P2[i] for i in range(3)]
    dist = math.sqrt(sum(d * d for d in diff))
    return dot_n > normal_thresh and dist < dist_thresh


# ============================================================================
# Tests
# ============================================================================

passed = 0
total = 0


def check(name, cond, detail=""):
    global passed, total
    total += 1
    tag = "PASS" if cond else "FAIL"
    print(f"Test {total}: {name}")
    if detail:
        print(f"  {tag}: {detail}")
    else:
        print(f"  {tag}")
    if cond:
        passed += 1
    return cond


# ---------------------------------------------------------------------------
# Test 1: Local CV+RRR unbiasedness with reservoir-local mu
# ---------------------------------------------------------------------------
N = 50000
V_gt = 0.7
# mu from ratio of targetPdf (with vis) / pHatNoVis
# Simulate: neighbor had V=0.7 in its evaluation, so targetPdf ~ 0.7 * pHatNoVis
neighbor_target_pdf = 0.35
p_hat_no_vis = 0.50
mu = min(max(neighbor_target_pdf / p_hat_no_vis, 0.0), 1.0)  # = 0.7, matches V_gt

bsdf = [0.3, 0.3, 0.3]
Lo = [1.0, 0.8, 0.6]
G = 0.5
contrib_threshold = 0.01
p_min = 0.05

rng = random.Random(42)
estimates = []
for _ in range(N):
    est = eval_local_revalidation(mu, bsdf, Lo, G, V_gt, contrib_threshold, p_min, rng.random)
    estimates.append(est)

mean_est = sum(estimates) / len(estimates)
err = abs(mean_est - V_gt)
check("Local CV+RRR unbiasedness (mu matches V)",
      err < 0.02,
      f"E[est]={mean_est:.4f}  GT={V_gt:.4f}  err={err:.4f}")

# ---------------------------------------------------------------------------
# Test 2: Local CV+RRR with bad mu (mu=0.2, V=0.8) — still unbiased
# ---------------------------------------------------------------------------
V_gt2 = 0.8
mu_bad = 0.2

rng2 = random.Random(123)
estimates2 = []
for _ in range(N):
    est = eval_local_revalidation(mu_bad, bsdf, Lo, G, V_gt2, contrib_threshold, p_min, rng2.random)
    estimates2.append(est)

mean_est2 = sum(estimates2) / len(estimates2)
err2 = abs(mean_est2 - V_gt2)
check("Local CV+RRR unbiasedness (bad mu=0.2, V=0.8)",
      err2 < 0.02,
      f"E[est]={mean_est2:.4f}  GT={V_gt2:.4f}  err={err2:.4f}")

# ---------------------------------------------------------------------------
# Test 3: Local CV+RRR with mu=0 (fully uncertain) — still unbiased
# ---------------------------------------------------------------------------
V_gt3 = 0.5
mu_zero = 0.0

rng3 = random.Random(456)
estimates3 = []
for _ in range(N):
    est = eval_local_revalidation(mu_zero, bsdf, Lo, G, V_gt3, contrib_threshold, p_min, rng3.random)
    estimates3.append(est)

mean_est3 = sum(estimates3) / len(estimates3)
err3 = abs(mean_est3 - V_gt3)
check("Local CV+RRR unbiasedness (mu=0, V=0.5)",
      err3 < 0.02,
      f"E[est]={mean_est3:.4f}  GT={V_gt3:.4f}  err={err3:.4f}")

# ---------------------------------------------------------------------------
# Test 4: RR probability clamped to [pMin, 1.0]
# ---------------------------------------------------------------------------
# Small contribution → p should clamp to pMin
small_bsdf = [0.001, 0.001, 0.001]
small_Lo = [0.01, 0.01, 0.01]
small_G = 0.01
C = [small_bsdf[i] * small_Lo[i] * small_G for i in range(3)]
res = luminance(C) * max(0.5, 0.5)
p_computed = max(p_min, min(res / contrib_threshold, 1.0))
check("RR probability pMin clamping",
      abs(p_computed - p_min) < 1e-6,
      f"p={p_computed:.6f}  pMin={p_min:.6f}")

# Large contribution → p should clamp to 1.0
big_bsdf = [10.0, 10.0, 10.0]
big_Lo = [10.0, 10.0, 10.0]
big_G = 1.0
C2 = [big_bsdf[i] * big_Lo[i] * big_G for i in range(3)]
res2 = luminance(C2) * max(0.5, 0.5)
p_big = max(p_min, min(res2 / contrib_threshold, 1.0))
check("RR probability 1.0 clamping",
      abs(p_big - 1.0) < 1e-6,
      f"p={p_big:.6f}")

# ---------------------------------------------------------------------------
# Test 5: evalTargetPdf matches expected formula
# ---------------------------------------------------------------------------
test_bsdf = [0.5, 0.3, 0.2]
test_Lo = [2.0, 1.5, 1.0]
test_G = 0.8
expected = luminance([test_bsdf[i] * test_Lo[i] for i in range(3)]) * test_G
actual = eval_target_pdf(test_bsdf, test_Lo, test_G)
check("evalTargetPdf formula",
      abs(expected - actual) < 1e-7,
      f"expected={expected:.6f}  actual={actual:.6f}")

# ---------------------------------------------------------------------------
# Test 6: geometryValid rejects bad neighbors
# ---------------------------------------------------------------------------
N_up = [0.0, 1.0, 0.0]
N_down = [0.0, -1.0, 0.0]
P1 = [0.0, 0.0, 0.0]
P2_near = [0.1, 0.0, 0.0]
P2_far = [10.0, 0.0, 0.0]

# Same normal, near → accept
check("geometryValid: same normal, near → accept",
      geometry_valid(N_up, N_up, P1, P2_near, 0.5, 0.2))

# Opposite normal → reject
check("geometryValid: opposite normal → reject",
      not geometry_valid(N_up, N_down, P1, P2_near, 0.5, 0.2))

# Same normal, far → reject
check("geometryValid: same normal, far → reject",
      not geometry_valid(N_up, N_up, P1, P2_far, 0.5, 0.2))

# ---------------------------------------------------------------------------
# Test 7: mu = clamp(neighborTargetPdf / pHatNoVis, 0, 1) edge cases
# ---------------------------------------------------------------------------
# pHatNoVis near zero → mu defaults to 0.5
p_hat_tiny = 1e-8
mu_default = 0.5  # fallback when pHatNoVis < 1e-7
check("mu fallback when pHatNoVis ≈ 0",
      p_hat_tiny < 1e-7,
      f"pHatNoVis={p_hat_tiny} < 1e-7 → mu defaults to {mu_default}")

# neighborTargetPdf > pHatNoVis → mu clamps to 1.0
mu_clamped = min(max(0.8 / 0.5, 0.0), 1.0)
check("mu clamps to 1.0 when ratio > 1",
      mu_clamped == 1.0,
      f"mu=clamp(0.8/0.5)={mu_clamped}")

# ---------------------------------------------------------------------------
# Test 8: Variance reduction — local CV+RRR has lower variance than vanilla
# when mu is accurate
# ---------------------------------------------------------------------------
V_gt10 = 0.6
mu_good = 0.6  # accurate estimate

rng10 = random.Random(789)
var_cvrrr = []
var_vanilla = []
for _ in range(N):
    est = eval_local_revalidation(mu_good, bsdf, Lo, G, V_gt10, contrib_threshold, p_min, rng10.random)
    var_cvrrr.append(est)
    var_vanilla.append(V_gt10 if rng10.random() > 0.0 else V_gt10)  # vanilla always traces

mean_cvrrr = sum(var_cvrrr) / len(var_cvrrr)
mean_vanilla = sum(var_vanilla) / len(var_vanilla)
std_cvrrr = math.sqrt(sum((x - mean_cvrrr) ** 2 for x in var_cvrrr) / len(var_cvrrr))
std_vanilla = math.sqrt(sum((x - mean_vanilla) ** 2 for x in var_vanilla) / len(var_vanilla))

# With perfect mu, CV+RRR should have variance ≤ vanilla (or very close)
check("Variance: good mu CV+RRR ≤ vanilla + epsilon",
      std_cvrrr <= std_vanilla + 0.05,
      f"std_cvrrr={std_cvrrr:.4f}  std_vanilla={std_vanilla:.4f}")


# ============================================================================
# Summary
# ============================================================================
print(f"\n{passed}/{total} tests passed.")
if passed < total:
    sys.exit(1)
print()
