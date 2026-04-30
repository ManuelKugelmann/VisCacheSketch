"""rank_cache_value.py - Rank step 14/15 variants by combined cache_value_score.

Score combines ray savings AND CV-correction value:
    cache_value_score = rays_saved_pct + max(0, vanilla_artifact_5_pct - 5) * k

Where k weights "how much credit to give for noise reduction on noisy scenes".
Default k=1.0 means: 1pp vanilla noise above 5pp threshold counts as 1pp ray
savings. Adjustable via env CACHE_VALUE_K=0.5 (de-emphasize) or 2.0 (emphasize).

Reads existing step 14 + step 15 stats.csv files; no re-render needed.
"""
import os, sys, io, csv, re
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

K = float(os.environ.get("CACHE_VALUE_K", "1.0"))
THRESH = 5.0  # pp — vanilla artifact below this gets no CV credit

def load(step):
    path = f"runtime/captures/ladder/{step}/stats.csv"
    if not os.path.exists(path): return []
    with open(path) as f: return list(csv.DictReader(f))

def parse_key(k):
    m = re.search(r"(CornellBox_[^_]+|BistroInterior|Sponza)_s_\d+_x(\d+)_.*pos_norm__pos__qa012__(.+)$", k)
    if not m: return None
    return m.group(1), int(m.group(2)), m.group(3)

rows = []
for step in ["14", "15"]:
    for r in load(step):
        k = r.get("key", "")
        if "baseline" in k.lower() or "vanilla" in k.lower(): continue
        p = parse_key(k)
        if not p: continue
        scene, spp, var = p
        try:
            rays = float(r.get("rays_traced_pct") or 100)
            van_art5 = float(r.get("vanilla_err_artifact_5_pct") or 0)
            err_d = float(r.get("err_minus_vanilla_pct") or 0)
            # Use new worse_artifact_5_pct if present; else fall back to
            # max(0, artifact_5_minus_vanilla_pct) (older proxy).
            w_raw = r.get("worse_artifact_5_pct")
            if w_raw is None or w_raw == "":
                a5d = float(r.get("artifact_5_minus_vanilla_pct") or 0)
                worse5 = max(0.0, a5d)
            else:
                worse5 = float(w_raw)
        except ValueError:
            continue
        rays_saved = 100.0 - rays
        cv_credit = max(0.0, van_art5 - THRESH) * K
        score = rays_saved + cv_credit
        rows.append({
            "step": step, "scene": scene, "spp": spp, "variant": var,
            "rays_saved": rays_saved, "van_art5": van_art5,
            "cv_credit": cv_credit, "score": score,
            "worse5": worse5, "err_d": err_d,
        })

# Per (scene, spp), top by score with worse5 <= 5pp.
groups = defaultdict(list)
for r in rows:
    if r["worse5"] <= 5.0:
        groups[(r["scene"], r["spp"])].append(r)

print(f"### cache_value_score = rays_saved + max(0, vanilla_artifact - {THRESH:.0f}) × {K} ###")
print(f"### Filter: worse_artifact_5 <= 5pp (no major regression) ###\n")
print(f"{'scene':<22} {'SPP':>3}  {'variant':<35} {'saved':>5} {'van5':>5} {'cv':>5} {'score':>6} {'worse5':>6}")
for (scene, spp), gs in sorted(groups.items()):
    gs.sort(key=lambda r: -r["score"])
    print(f"--- {scene} x{spp} ---")
    for r in gs[:5]:
        print(f"{scene:<22} x{spp:<2} {r['variant']:<35} {r['rays_saved']:>4.0f}% "
              f"{r['van_art5']:>4.0f}% {r['cv_credit']:>4.0f}pp "
              f"{r['score']:>5.0f}  {r['worse5']:>5.2f}pp")
    print()
