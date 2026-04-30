"""rank_balance.py - Find best cache wins at equal compute.

For each cache variant:
  effective_spp     = src_spp x (rays_traced_pct / 100)
  vanilla_at_eff    = vanilla_err_pct at the nearest available eff_spp
  eq_cost_delta     = cache_err_pct - vanilla_at_eff
                       (negative = cache wins at same compute)

Ranking: most-negative eq_cost_delta first, allow worse5 up to LOOSE_WORSE_LIMIT
(default 15pp) to explore the "few artifacts" space — strict 0pp filter was
too narrow per user 2026-04-28.

No artificial rays-saved targeting. Each scene/SPP picks its natural best.

Usage:
  runtime/pythondist/python.exe scripts/rank_balance.py
"""
import os, sys, io, csv, re
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LOOSE_WORSE_LIMIT = float(os.environ.get("WORSE_LIMIT", "15.0"))   # pp
AVAILABLE_VAN_SPP = [1, 2, 4, 8, 16]

def nearest_van(eff):
    return min(AVAILABLE_VAN_SPP, key=lambda s: abs(s - eff))

def parse_key(k):
    m = re.search(r"(CornellBox_[^_]+|BistroInterior|Sponza)_s_\d+_x(\d+)_.*pos_norm__pos__qa012__(.+)$", k)
    if not m: return None
    return m.group(1), int(m.group(2)), m.group(3)

# Aggregate cache rows across step 14 + 15.
all_rows = []
for step in ["14", "15"]:
    p = f"runtime/captures/ladder/{step}/stats.csv"
    if not os.path.exists(p): continue
    with open(p) as f:
        all_rows.extend(list(csv.DictReader(f)))

# Build vanilla-err table: (scene, src_spp) -> vanilla_err_pct.
# Each row carries vanilla_err_pct at the SAME spp it ran at; we treat that
# as the per-(scene, spp) vanilla baseline.
vanilla = {}
for r in all_rows:
    p = parse_key(r.get("key", ""))
    if not p: continue
    scene, spp, _ = p
    try:
        v = float(r.get("vanilla_err_pct") or 0)
        if v > 0: vanilla[(scene, spp)] = v
    except ValueError: pass

ranked = []
for r in all_rows:
    p = parse_key(r.get("key", ""))
    if not p: continue
    scene, spp, var = p
    try:
        rays = float(r.get("rays_traced_pct") or 100)
        cache_err = float(r.get("error_delta_pct") or 0)
        w_raw = r.get("worse_artifact_5_pct")
        if w_raw and w_raw.strip():
            worse5 = float(w_raw)
        else:
            worse5 = max(0.0, float(r.get("artifact_5_minus_vanilla_pct") or 0))
    except ValueError: continue
    eff = spp * rays / 100.0
    eff_spp = nearest_van(eff)
    van_eff = vanilla.get((scene, eff_spp))
    van_same = vanilla.get((scene, spp))
    if van_eff is None or van_same is None: continue
    eq_cost = cache_err - van_eff       # cache vs vanilla at equal compute
    same_spp_d = cache_err - van_same   # cache vs vanilla at same SPP
    rays_saved = 100 - rays
    ranked.append({
        "scene": scene, "src_spp": spp, "eff_spp": eff_spp, "variant": var,
        "rays": rays, "rays_saved": rays_saved,
        "cache_err": cache_err, "van_eff": van_eff, "van_same": van_same,
        "same_spp_d": same_spp_d, "eq_cost": eq_cost, "worse5": worse5,
    })

# Group by (scene, src_spp), sort by eq_cost ascending (best first), allow
# loose worse5 (up to LOOSE_WORSE_LIMIT) to admit "few artifacts" winners.
groups = defaultdict(list)
for r in ranked: groups[(r["scene"], r["src_spp"])].append(r)

# Interesting score combines equal-cost win (primary), same-SPP win
# (secondary), and rays-saved (bonus). worse5 above WORSE_SOFT pp is
# softly penalized.
WORSE_SOFT = 10.0
def interest(r):
    base = -r["eq_cost"] - 0.5 * r["same_spp_d"]
    rays_bonus = 0.05 * r["rays_saved"]
    art_penalty = 2.0 * max(0, r["worse5"] - WORSE_SOFT)
    return base + rays_bonus - art_penalty

print(f"### INTERESTING CONFIGS — balance of rays_saved, same-SPP Δ, equal-cost Δ ###")
print(f"### Allow worse5 <= {LOOSE_WORSE_LIMIT:.0f}pp; soft penalty above {WORSE_SOFT:.0f}pp ###\n")
print(f"{'scene':<22} {'src':>3}  {'variant':<33} {'saved':>5} {'eff':>4} {'cache':>5} {'sameΔ':>6} {'eqΔ':>6} {'worse5':>6} {'score':>5}")

for (scene, spp), gs in sorted(groups.items()):
    safe = [r for r in gs if r["worse5"] <= LOOSE_WORSE_LIMIT]
    if not safe: safe = gs
    safe.sort(key=lambda r: -interest(r))
    print(f"--- {scene} src=x{spp} ({len(safe)} <= {LOOSE_WORSE_LIMIT:.0f}pp) ---")
    for r in safe[:5]:
        print(f"{scene:<22} x{r['src_spp']:<2} {r['variant']:<33} {r['rays_saved']:>4.0f}% "
              f"x{r['eff_spp']:<3} {r['cache_err']:>4.1f}% {r['same_spp_d']:>+5.1f} "
              f"{r['eq_cost']:>+5.1f} {r['worse5']:>5.2f} {interest(r):>5.1f}")
    print()
