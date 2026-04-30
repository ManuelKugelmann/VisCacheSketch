"""rank_equal_cost.py - Compare each cache variant against vanilla at matching ray cost.

Equal-cost comparison:
  effective_spp = cache_spp × (rays_traced_pct / 100)

For each cache variant, look up the vanilla baseline at the nearest available
effective SPP (we have x1, x2, x4, x8, x16 from step 0). Compute:
  equal_cost_err_delta = cache_err_pct - vanilla_err_pct[effective_spp_rounded]

Negative = cache wins at same compute. Positive = cache wastes the budget vs
just running more samples through vanilla.

Usage:
  runtime/pythondist/python.exe scripts/rank_equal_cost.py [STEP=14]
"""
import os, sys, io, csv, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

STEP = sys.argv[1] if len(sys.argv) > 1 else "14"

# Read step's cache variants.
def load_cache(step):
    p = f"runtime/captures/ladder/{step}/stats.csv"
    if not os.path.exists(p): return []
    with open(p) as f: return list(csv.DictReader(f))

# Read vanilla baselines per scene/SPP from compute_render_error_signed_hdr
# values stored alongside each cache row (vanilla_err_pct field). For
# cache (scene, src_spp, rays), the matching effective SPP comes from
# rounding cache_spp × rays/100 to nearest available {1, 2, 4, 8, 16}.
AVAILABLE_VAN_SPP = [1, 2, 4, 8, 16]

def nearest_van_spp(eff):
    return min(AVAILABLE_VAN_SPP, key=lambda s: abs(s - eff))

# Per (scene, target_spp) — collect cache rows + vanilla error at that SPP.
# vanilla_err_pct from cache row is at the SAME spp; we need it at the
# EFFECTIVE spp. Look it up from the (scene, eff_spp) cache row's
# vanilla_err_pct field — the vanilla error is the same regardless of which
# cache variant ran at that SPP.

def parse_key(k):
    m = re.search(r"(CornellBox_[^_]+|BistroInterior|Sponza)_s_\d+_x(\d+)_.*pos_norm__pos__qa012__(.+)$", k)
    if not m: return None
    return m.group(1), int(m.group(2)), m.group(3)

cache_rows = load_cache(STEP)

# Build vanilla err table: (scene, spp) -> vanilla_err_pct (any cache row at
# that scene/spp will have it).
vanilla_err = {}
for r in cache_rows:
    p = parse_key(r.get("key", ""))
    if not p: continue
    scene, spp, _ = p
    try:
        v = float(r.get("vanilla_err_pct") or 0)
        vanilla_err[(scene, spp)] = v
    except ValueError:
        pass

# Now rank each cache variant by equal-cost delta.
out = []
for r in cache_rows:
    p = parse_key(r.get("key", ""))
    if not p: continue
    scene, spp, var = p
    try:
        rays = float(r.get("rays_traced_pct") or 100)
        cache_err = float(r.get("error_delta_pct") or 0)
        # Step 14 uses error_delta_pct as absolute cache error vs GT (per
        # the changed semantics in compute_render_error_signed_hdr).
        worse5 = float(r.get("worse_artifact_5_pct") or
                       max(0.0, float(r.get("artifact_5_minus_vanilla_pct") or 0)))
    except ValueError:
        continue
    eff = spp * rays / 100.0
    eff_spp = nearest_van_spp(eff)
    van_at_eff = vanilla_err.get((scene, eff_spp))
    if van_at_eff is None:
        continue
    eq_cost_delta = cache_err - van_at_eff
    out.append({
        "scene": scene, "src_spp": spp, "eff_spp": eff_spp, "variant": var,
        "rays": rays, "cache_err": cache_err, "van_err": van_at_eff,
        "eq_cost_delta": eq_cost_delta, "worse5": worse5,
    })

# Print per scene/spp, sorted by eq_cost_delta ascending (best cache wins).
from collections import defaultdict
groups = defaultdict(list)
for r in out:
    groups[(r["scene"], r["src_spp"])].append(r)

print(f"### EQUAL-COST: cache_err vs vanilla at effective SPP (rounded to {{1,2,4,8,16}}) ###")
print(f"### Negative eq_cost_delta = cache wins at same compute ###\n")
print(f"{'scene':<22} {'src':>3} {'variant':<35} {'rays':>5} {'eff':>4} {'cache':>5} {'van@eff':>7} {'Δ_cost':>7} {'worse5':>6}")
for (scene, spp), gs in sorted(groups.items()):
    gs.sort(key=lambda r: r["eq_cost_delta"])
    print(f"--- {scene} src=x{spp} ---")
    for r in gs[:5]:
        print(f"{scene:<22} x{r['src_spp']:<2} {r['variant']:<35} {r['rays']:>4.0f}% "
              f"x{r['eff_spp']:<3} {r['cache_err']:>4.1f}% {r['van_err']:>6.1f}% "
              f"{r['eq_cost_delta']:>+6.1f}pp {r['worse5']:>5.2f}pp")
    print()

# Bonus: variants in the 50%-rays-saved band (widened to [30, 70]% for more hits).
print("\n### ~50%-RAYS-SAVED BAND (rays_traced ∈ [30, 70]%) per scene/SPP ###")
print(f"{'scene':<22} {'src':>3} {'variant':<35} {'rays':>5} {'eff':>4} {'cache':>5} {'van@eff':>7} {'Δ_cost':>7} {'worse5':>6}")
for (scene, spp), gs in sorted(groups.items()):
    band = [r for r in gs if 40.0 <= r["rays"] <= 60.0]
    if not band: continue
    band.sort(key=lambda r: r["eq_cost_delta"])
    print(f"--- {scene} src=x{spp} ({len(band)} in band) ---")
    for r in band[:3]:
        print(f"{scene:<22} x{r['src_spp']:<2} {r['variant']:<35} {r['rays']:>4.0f}% "
              f"x{r['eff_spp']:<3} {r['cache_err']:>4.1f}% {r['van_err']:>6.1f}% "
              f"{r['eq_cost_delta']:>+6.1f}pp {r['worse5']:>5.2f}pp")
    print()
