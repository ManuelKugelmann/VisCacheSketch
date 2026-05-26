# GRIS × VCM with reconnection-shift kernel collapse

_Forward-looking design note. Not implemented. Prereqs: per-cell partial-path
storage (`project_partial_path_cell.md`), ReSTIR BDPT light subpaths
(`LADDER_PLAN.md` Stage G)._

---

## 1. The idea in one paragraph

Vertex Connection and Merging [Georgiev et al. 2012; Hachisuka et al. 2012]
unifies bidirectional connections and photon merging through MIS. Merging needs
a **kernel radius** `r` because two independently sampled subpaths almost never
meet exactly; you accept a light vertex within `r` of the query vertex and weight
by a density-estimation kernel. That radius is the source of PM's bias
(`O(r²)`). The classical consistency story shrinks `r → 0` progressively across
iterations, trading the bias for variance (`O(1/(N r²))`) and needing `N → ∞`.

This note proposes a different lever for the shrink. **The merge kernel is not a
property of the cache cell** — the multilevel hashmap is purely a world-space
lookup accelerator (SHaRC / Boissé role: find candidate light vertices near an
eye-path query). Instead, the kernel radius is **per-candidate**, and ReSTIR PT's
**reconnection shift** [Lin et al. 2022] drives it toward zero: shift the stored
light subpath so its merge vertex reconnects *exactly* onto the query path. Where
the shift is feasible the kernel collapses to a delta — an exact, zero-bias
connection. Where it is infeasible (specular chains, grazing angles) a finite
merge kernel survives as a density-estimation fallback. GRIS supplies the
unbiased resampling-MIS combination across the two regimes. The path mutation
routes each path to its lowest-bias estimator, so **bias concentrates only on the
genuinely unreconnectable subset — exactly where photon density estimation is the
right tool anyway.**

---

## 2. Merge and connect are one shift family, not two algorithms

In GRIS, a candidate is a sample in path space with a target `p̂` and a shift map
`T` carrying it from its donor domain into the receiver domain, with Jacobian
`|∂T/∂·|`. The two VCM techniques are both shift maps differing only in `r`:

- **Connection (`r = 0`).** The reconnection shift redirects the stored light
  vertex's outgoing segment to point exactly at the query vertex. Deterministic;
  the connecting segment is fixed. This is Lin 2022's reconnection shift verbatim.
- **Merge (`r > 0`).** Accept a stored vertex `y` within `r` of query vertex `x`;
  contribute `f · K_r(‖x − y‖)` where `K_r` is a normalized density kernel
  (`∫ K_r = 1` over the tangent disk). Effective pdf folds in the photon density
  and the kernel normalization.

The merge **is** the connection convolved with `K_r`. Collapsing `r` un-blurs it.
If `K_r → δ` as `r → 0` (§5), the merge candidate's contribution converges
*continuously* to the connection candidate's. So we never glue two incompatible
estimators — we evaluate one family indexed by a per-candidate `r`, and `r` is the
knob the mutation turns.

---

## 3. The hashmap is storage, not kernel

The multilevel spatial hash stores light-subpath vertices (photons) with their
generating seed for replay — the `(rcVertex, initRandomSeed)` payload from
`project_partial_path_cell.md`. Its only jobs:

1. **Spatial lookup** — given an eye-path query vertex, return candidate light
   vertices in a neighbourhood. The neighbourhood is the *search* radius (how far
   the hash returns candidates), deliberately **decoupled** from the *kernel*
   radius `r` (how those candidates are weighted). Search radius = the cell
   footprint at the queried cascade level; kernel radius = per-candidate, §5.
2. **Visibility oracle** — the connection's would-be shadow ray `V(x, y)` is a
   VisCache query, resolved by CV+RRR rather than always traced. This is where
   VisCache earns its place: the kernel-collapse feasibility test needs visibility,
   and the cache makes that test cheap.

Crucially the cell footprint no longer doubles as the merge kernel (the framing
rejected in `project_partial_path_cell.md` payoff #3). Cells bound the *candidate
set*; the shift sets the *bias*.

---

## 4. The r→0 pdf ramp — problem statement

Mixing a `r = 0` connection candidate (a delta in path-space measure) and a
`r > 0` merge candidate (an area-density estimate) inside one GRIS reservoir
requires a **common measure**. This is the BPT-vs-PM measure mismatch VCM solves
with per-path MIS; under GRIS the obligation moves into the resampling weights.

Three things must hold for the reservoir math to be valid:

1. **Common measure.** Every candidate's pdf must be expressed in the same
   unified path-space measure, with the kernel-area term included in the merge
   candidate's pdf. Otherwise the resampling weight `w_i = m_i · p̂_i · W_i` mixes
   units and the estimator is not unbiased.
2. **Continuity at the limit.** As `r → 0` the merge candidate's pdf, target `p̂`,
   and shift Jacobian must each converge to the connection candidate's. Then the
   connection's MIS weight is simply `lim_{r→0}` of the merge's — no special case.
3. **Bounded variance along the ramp.** The merge variance `∝ 1/(N r²)` diverges
   as `r → 0` at fixed photon count `N`. The ramp must avoid paying that on the
   branch it drives to zero.

(3) is the one that looks fatal and isn't: the connection branch has **no kernel
and no density estimation**, so it has no `1/(N r²)` term at all. We only ever
hold `r` finite on candidates where connection *failed* — and there we *keep* `r`
away from zero. So small-`r` and finite-`N` never coexist on the same candidate.
The ramp escapes the classical PPM variance blowup by construction.

That leaves (1) and (2): we need a kernel family whose `r → 0` limit is a true
delta with the normalization preserved. That is precisely a **nascent delta**.

---

## 5. The r→0 pdf ramp — proposed solutions

### 5.1 Nascent-delta kernel family (the core fix)

Pick `K_r` from a **Dirac delta sequence**: `∫ K_r = 1` for all `r > 0`, and
`K_r → δ` weakly as `r → 0`. Then merge → connect continuously and (1)+(2) hold by
the convergence of the family itself, not by a gluing argument. Candidates:

| kernel | `K_r(u)` (2D, `‖u‖ = d`) | support | notes |
|---|---|---|---|
| **Gaussian** | `(1/2πr²)·exp(−d²/2r²)` | infinite | C∞, cleanest for the limit proof; transcendental on GPU |
| **Epanechnikov** | `(2/πr²)·(1 − d²/r²)₊` | compact `[0,r]` | AMISE-optimal density kernel; the "right" finite-`r` choice |
| **Wendland C²** | `(7/πr²)·(1 − d/r)₊⁴·(1 + 4d/r)` | compact `[0,r]` | **GPU pick** — polynomial, C², support = hash search radius |
| Box (constant disk) | `1/πr²` on `d ≤ r` | compact | classical PPM; crudest nascent delta, discontinuous |

Recommendation: **Wendland C² for the implementation** (compact support lets the
spatial-hash search radius equal the kernel support exactly — no candidates wasted
beyond `r`; C² gives a smooth Jacobian for the GRIS shift), **Gaussian for the
derivation** (the cleanest `K_r → δ` proof), **Epanechnikov as the variance-optimal
reference** to benchmark the finite-`r` fallback against. All four preserve
`∫ K_r = 1`, so the merge candidate's pdf carries a clean `1/area`-scaled mass that
becomes the delta normalization in the limit.

### 5.2 Feasibility → radius map

Make `r` a continuous, monotone function of a per-candidate **reconnection
feasibility** score, so the mutation "nudges toward zero" smoothly rather than
flipping a mode:

```
r(s) = r_max · (1 − s)^γ ,   s ∈ [0,1]
s = s_rough · s_vis · s_jac
```

- `s_rough` — Lin 2022 `rcVertex` roughness test: 1 when both endpoints are rough
  enough that the connection's BSDF product is well-behaved, → 0 toward specular.
- `s_vis` — VisCache `μ` for `V(x, y)` (the would-be connection's visibility);
  near-occluded connections get a wider kernel rather than a confident delta.
- `s_jac` — a bound on the reconnection-shift Jacobian variance; large Jacobian
  (grazing, near-singular reconnection) keeps `r` finite to avoid a spike.

`s = 1` → `r = 0` → delta connection. `s = 0` → `r = r_max` → full PM kernel.
`γ` shapes how aggressively the kernel collapses as feasibility rises.

### 5.3 One reservoir, shared MIS

Connection and merge are candidates in **one** GRIS reservoir. Generalized
pairwise / balance-heuristic MIS [Lin 2022] over their shift Jacobians combines
them; the connection's MIS weight is the `r → 0` limit of the merge's (§4.2).
No second reservoir, no post-hoc blend — the resampling weight handles it.

### 5.4 Numerical floor `r_min` (optional safety)

To never literally evaluate a delta / divide by zero on the GPU, hold
`r ≥ r_min` on the *merge* branch. The connection branch (`s` above threshold)
still takes a genuine deterministic connection. `r_min` injects `O(r_min²)` bias
**only on the merge branch**, progressively shrinkable across accumulated frames in
the PPM sense — and harmless on the connection branch, which never touches `r_min`.

### 5.5 Visibility decoupling via VisCache

The feasibility test (§5.2 `s_vis`) and the connection's shadow ray are the same
query. Resolve both through VisCache CV+RRR so the kernel-collapse decision costs a
cache read in the common case, falling back to a traced ray only at the variance-
gated rate. This is the integration point that ties the scheme to the existing
cache rather than bolting on a separate visibility pass.

### 5.6 Instant radiosity / VPL — the connection branch is already a known object

The `r = 0` branch **is** instant radiosity [Keller 1997]: a stored light vertex
used as a connection target is a virtual point light, and connecting an eye vertex
to it is a deterministic VPL gather (a delta in direction). This is not a loose
analogy — it gives us decades of VPL machinery to reuse, and it identifies *where*
the ramp must open, from the opposite side of the same coin:

- **The VPL singularity is the merge's reason to exist.** A VPL gather has geometry
  term `G = cosθ·cosθ′/d²`, which blows up as the eye vertex approaches the VPL
  (`d → 0`) — the classic IR splotch/firefly. The standard remedy is **bias
  clamping** (bound `G`), an ad-hoc, energy-losing bias. In our scheme this is
  exactly the region where feasibility should *lower* and the kernel should
  **open** (`r > 0`): the merge branch is the **principled replacement for VPL
  clamping**. Instead of clamping `G`, we transition smoothly into a
  density-estimation kernel whose `O(r²)` bias is controlled and recoverable. So
  the feasibility map (§5.2) gains a near-field term: small `d` / large `G` →
  lower `s` → finite `r`. The connection branch keeps the unbiased far field; the
  merge branch absorbs the near-field singularity. **The two VCM techniques split
  the integrand exactly along the VPL bias-clamp boundary.**
- **Reuse bias compensation.** Bidirectional VPL bias compensation
  [Kollig & Keller 2004] re-captures the clamped near-field residual with a
  short-path correction. The merge branch is structurally that residual
  estimator — the energy the clamped connection drops is what the kernel gather
  recovers. Worth checking whether their residual formulation drops straight into
  the merge candidate's target `p̂`.
- **Virtual Sphere / Ray Lights are independent prior art for the same continuum.**
  VSL [Hašan et al. 2009] and VRL [Novák et al. 2012] deliberately *spread* a VPL
  from a point into a sphere/ray precisely to kill the `d → 0` singularity — i.e.
  they already convolve the delta with a finite kernel. A virtual sphere light is
  a merge candidate derived from the VPL side. This (a) is a citation anchor
  showing the continuous delta↔kernel family is established, and (b) hands us
  another nascent-delta kernel shape (the sphere kernel) for §5.1.
- **The hashmap + GRIS reservoir subsumes lightcuts.** Scalable many-VPL gather
  (Lightcuts [Walter et al. 2005]; matrix row-column [Hašan et al. 2007]) clusters
  VPLs to bound cost. Our world hash + reservoir resampling is the reservoir-era
  analogue: rather than build a cut, the reservoir resamples VPL candidates
  (world-space ReSTIR DI / ReGIR over the stored vertices). The acceleration
  structure we already have replaces the lightcut tree.

Net: the scheme is **instant radiosity (connection / VPL branch) + photon mapping
(merge branch), unified by GRIS, with `r` as the single continuous regularizer
mediating between the VPL singularity and PM bias.** The reconnection shift is what
makes `r` per-candidate and feasibility-driven rather than a global clamp.

---

## 6. Open proof obligations / risks

- **Jacobian continuity.** Must verify the reconnection-shift Jacobian is the
  `r → 0` limit of the merge "shift" Jacobian under the chosen parametrization.
  This is the crux of §4.2 and the paper-grade obligation; if it fails, the MIS
  weights are discontinuous at the limit and the clean "connection = limit of
  merge" story breaks. Derive with the Gaussian family first (§5.1).
- **Target-function choice.** GRIS needs a `p̂` defined on both branches. The
  natural choice is unshadowed path contribution × kernel mass; confirm it keeps
  the support condition (every contributing path reachable) across the ramp.
- **Search-vs-kernel radius interaction.** Decoupling them (§3) is correct but the
  hash must return enough candidates to populate the merge branch where `r` is
  large; tie the cascade-level selection to `r_max`, not to the per-candidate `r`.
- **Temporal photon reuse.** Real-time means photons are regenerated/accumulated
  per frame in the world hash; the `r_min` shrink schedule (§5.4) must be driven by
  the *accumulated* temporal photon count, not per-frame count.

---

## 7. Relation to prior work and to our stack

- **Anchors:** VCM [Georgiev et al. 2012] already MIS-combines connect + merge;
  instant radiosity [Keller 1997] is the connection branch; Virtual Sphere/Ray
  Lights [Hašan 2009; Novák 2012] already place a delta↔kernel continuum on the
  VPL side. New here: (1) **GRIS resampling** in place of per-path MIS, letting a
  reservoir carry both techniques; (2) **feasibility-driven adaptive `r` per
  candidate** driving toward a delta, instead of a global progressive radius or a
  fixed VPL clamp; (3) the **world-space hashmap as pure accelerator + VisCache as
  visibility oracle**; (4) the merge kernel reframed as the **principled
  replacement for VPL bias clamping** (§5.6). Not present in any of the 8 GRIS
  codebases surveyed in `project_partial_path_cell.md`.
- **Builds on:** per-cell partial-path storage (the photon payload + replay),
  reconnection/hybrid shift (the kernel-collapse operator), VisCache CV+RRR (the
  feasibility/visibility oracle), the multilevel cascade (candidate-set scoping).
- **Sequencing:** prerequisite is Stage F (ReSTIR PT reconnection-shift V
  revalidation) landing and the BDPT light-subpath pass existing
  (`LADDER_PLAN.md` Stage G). Then: store light subpaths in the world hash →
  add the merge branch with a Wendland kernel → wire the feasibility→radius map →
  validate the `r → 0` Jacobian continuity on Cornell before scene scaling.
