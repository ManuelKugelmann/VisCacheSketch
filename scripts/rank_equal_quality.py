"""rank_equal_quality.py — Rays saved at equal-quality vs vanilla (multi-metric).

Quality = error AND noise AND artifact_5. For each cache variant:
  equiv_spp[m]   = SPP at which vanilla matches cache value on metric m
  overall_equiv  = max(equiv_spp_err, equiv_spp_noise, equiv_spp_artifact)
                   (the binding constraint — vanilla needs that many SPPs to
                    match cache on the WORST of the three dimensions)
  rays_saved%    = 100 × (1 − cache_rays_per_pixel / overall_equiv)

If a cache metric is *worse* than vanilla at every measured SPP, equiv_spp on
that dimension is ≤ 1 (extrapolated) — overall_equiv collapses to the failing
dim and rays_saved goes negative. That's the artifact-bound regime (e.g.
cell16x16 ct=2 trades savings for visible regional regression).

Vanilla curves are built per scene from cache rows' vanilla_* fields aggregated
across all measured SPPs (each cache row at (scene, spp) carries vanilla
metrics at that SPP — they're variant-invariant). Log-linear interp in spp.

Usage:
  runtime/pythondist/python.exe scripts/rank_equal_quality.py [STEP=14]
  STEPS=14,15,17,18 runtime/.../rank_equal_quality.py
"""
import os, sys, io, csv, re, math
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

STEPS = os.environ.get("STEPS", "").split(",") if os.environ.get("STEPS") else None
if not STEPS:
    STEPS = [sys.argv[1]] if len(sys.argv) > 1 else ["14"]

WORSE5_LIMIT = float(os.environ.get("WORSE5_LIMIT", "20.0"))

def parse_key(k):
    m = re.search(r"(CornellBox_[^_]+|BistroInterior|BistroExterior|Sponza)_s_\d+_x(\d+)_.*pos_norm__pos__qa012__(.+)$", k)
    if not m: return None
    return m.group(1), int(m.group(2)), m.group(3)

# ----- Build per-scene vanilla curves from cache-row vanilla_* fields. -----
# (scene, spp) -> {err: ..., noise: ..., art5: ...} (vanilla values, identical
# across cache variants at the same scene/spp).
vanilla_at = {}
def _f(r, k, d=None):
    v = r.get(k, "")
    try: return float(v) if v not in ("", None) else d
    except ValueError: return d

all_rows = []
for step in STEPS:
    p = f"runtime/captures/ladder/{step}/stats.csv"
    if not os.path.exists(p): continue
    with open(p) as f:
        for r in csv.DictReader(f):
            r["__step"] = step
            all_rows.append(r)
            pk = parse_key(r.get("key", ""))
            if not pk: continue
            scene, spp, _ = pk
            van = vanilla_at.setdefault((scene, spp), {})
            for short, key in (("err",   "vanilla_err_pct"),
                               ("noise", "vanilla_noise_pct"),
                               ("art5",  "vanilla_err_artifact_5_pct")):
                v = _f(r, key)
                if v is not None and v > 0:
                    van[short] = v

# Augment with step 00 baseline (mean_err_pct + mean_noise_pct; no artifact column).
p00 = "runtime/captures/ladder/00/stats.csv"
if os.path.exists(p00):
    with open(p00) as f:
        for r in csv.DictReader(f):
            try:
                spp = int(r.get("spp") or 0)
            except ValueError: continue
            scene = r.get("scene") or ""
            if not scene or spp <= 0 or spp == 4096: continue
            van = vanilla_at.setdefault((scene, spp), {})
            e = _f(r, "mean_err_pct"); n = _f(r, "mean_noise_pct")
            if e and e > 0: van.setdefault("err", e)
            if n and n > 0: van.setdefault("noise", n)

# Per-scene curve per metric: list of (spp, value) sorted by spp.
curves = defaultdict(lambda: defaultdict(list))
for (scene, spp), van in vanilla_at.items():
    for m, v in van.items():
        curves[scene][m].append((spp, v))
for s in curves:
    for m in curves[s]: curves[s][m].sort()

def equiv_spp_for(scene, metric, target):
    """SPP where vanilla[metric] equals target. Log-log interp; extrapolates
    at both ends. Returns None if curve missing or target ≤ 0."""
    pts = curves.get(scene, {}).get(metric)
    if not pts or target <= 0: return None
    # vanilla is monotone-decreasing in spp. Bracket the target.
    if target >= pts[0][1]:
        if len(pts) < 2: return float(pts[0][0])
        s1, e1 = pts[0]; s2, e2 = pts[1]
    elif target <= pts[-1][1]:
        if len(pts) < 2: return float(pts[-1][0])
        s1, e1 = pts[-2]; s2, e2 = pts[-1]
    else:
        s1 = e1 = s2 = e2 = None
        for i in range(len(pts) - 1):
            if pts[i][1] >= target >= pts[i + 1][1]:
                s1, e1 = pts[i]; s2, e2 = pts[i + 1]; break
        if s1 is None: return float(pts[-1][0])
    if e1 <= 0 or e2 <= 0 or s1 <= 0 or s2 <= 0 or e1 == e2:
        return float(s1)
    t = (math.log(target) - math.log(e1)) / (math.log(e2) - math.log(e1))
    return math.exp(math.log(s1) + t * (math.log(s2) - math.log(s1)))

# ----- Score each cache row. -----
ranked = []
for r in all_rows:
    pk = parse_key(r.get("key", ""))
    if not pk: continue
    scene, spp, var = pk
    rays = _f(r, "rays_traced_pct", 100.0)
    cache_err = _f(r, "error_delta_pct")
    cache_noise = _f(r, "noise_delta_pct")
    cache_art5 = _f(r, "error_artifact_5_pct")
    worse5 = _f(r, "worse_artifact_5_pct",
                max(0.0, _f(r, "artifact_5_minus_vanilla_pct", 0.0)))
    if cache_err is None: continue

    eq_err = equiv_spp_for(scene, "err",   cache_err)
    eq_n   = equiv_spp_for(scene, "noise", cache_noise) if cache_noise else None
    eq_a   = equiv_spp_for(scene, "art5",  cache_art5)  if cache_art5  else None
    parts = [(name, val) for name, val in (("err", eq_err), ("noise", eq_n), ("art5", eq_a))
             if val is not None]
    if not parts: continue
    # Binding constraint = the metric that needs the MOST vanilla SPPs to match.
    binding_name, binding_spp = max(parts, key=lambda nv: nv[1])

    cache_rays_pp = spp * rays / 100.0
    saved_pct = 100.0 * (1.0 - cache_rays_pp / max(binding_spp, 1e-6))
    ranked.append({
        "step": r["__step"], "scene": scene, "src_spp": spp, "variant": var,
        "rays": rays, "cache_err": cache_err, "cache_art5": cache_art5,
        "cache_noise": cache_noise,
        "eq_err": eq_err, "eq_noise": eq_n, "eq_art5": eq_a,
        "binding": binding_name, "binding_spp": binding_spp,
        "saved_pct": saved_pct, "worse5": worse5,
    })

# ----- Group + print. -----
groups = defaultdict(list)
for r in ranked: groups[(r["scene"], r["src_spp"])].append(r)

print(f"### EQUAL-QUALITY (multi-metric: err ∧ noise ∧ artifact_5) ###")
print(f"### binding = metric that demands MOST vanilla SPPs to match cache ###")
print(f"### worse5 ceiling = {WORSE5_LIMIT:.0f}pp (env WORSE5_LIMIT) ###\n")
hdr = (f"{'st':>2} {'variant':<46} {'rays':>5} {'cE':>5} {'cN':>5} {'cA':>5} "
       f"{'eqE':>5} {'eqN':>5} {'eqA':>5} {'bnd':>5} {'@spp':>6} {'saved%':>7} {'w5':>5}")
for (scene, spp), gs in sorted(groups.items()):
    safe = [r for r in gs if r["worse5"] <= WORSE5_LIMIT]
    if not safe: safe = gs
    safe.sort(key=lambda r: -r["saved_pct"])
    print(f"--- {scene}  src=x{spp}  ({len(safe)} ≤ {WORSE5_LIMIT:.0f}pp w5) ---")
    print(hdr)
    for r in safe[:5]:
        ee = f"{r['eq_err']:>5.1f}" if r['eq_err'] else "  -  "
        en = f"{r['eq_noise']:>5.1f}" if r['eq_noise'] else "  -  "
        ea = f"{r['eq_art5']:>5.1f}" if r['eq_art5'] else "  -  "
        cn = f"{r['cache_noise']:>5.2f}" if r['cache_noise'] else "  -  "
        ca = f"{r['cache_art5']:>5.2f}" if r['cache_art5'] else "  -  "
        print(f"{r['step']:>2} {r['variant'][:45]:<46} {r['rays']:>4.0f}% "
              f"{r['cache_err']:>5.2f} {cn} {ca} "
              f"{ee} {en} {ea} {r['binding']:>5} {r['binding_spp']:>5.1f}  "
              f"{r['saved_pct']:>+6.1f}% {r['worse5']:>5.2f}")
    print()
