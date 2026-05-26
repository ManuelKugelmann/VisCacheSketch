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

This is the same move [Xing et al. 2024] make in Differentiable Photon Mapping:
they formalize the merge as a path-sampling technique with a **smooth
differentiable density-estimation kernel** and a well-defined pdf, precisely so the
merge has derivatives. We need the same smoothness for a *different* reason — the
`r → 0` Jacobian-continuity limit (§8) — but it is the same kernel requirement, and
their formalization is a ready citation that "merge = smooth kernel over a measure"
is established, not invented here.

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

### 5.7 Specular branch: manifold reconnection — the SDS core is not irreducible

The merge branch was justified (§6, §8) as the only estimator for the
SDS / pure-specular core, where a specular BSDF is a delta and ordinary connection
has zero pdf. That core is **smaller than it looks**: you can recover those paths
*unbiased* by **solving** for the specular chain joining two endpoints instead of
sampling it.

- **Specular Manifold Sampling** [Zeltner, Georgiev & Jakob 2020] — stochastic
  Newton walk on the manifold of valid specular subpaths; unbiased variant via a
  Bernoulli inverse-probability estimator; handles SDS and glints.
- **Specular Polynomials** [Fan et al. 2024] — Newton-free: reformulates the
  specular constraint as a univariate polynomial system, finds the *complete* set
  of admissible chains by root-finding. Deterministic, GPU-friendly; removes SMS's
  initialization dependence and missed-root bias.
- **Manifold Path Guiding** [Fan et al. 2023] for importance-sampling long chains;
  **Manifold NEE** [Hanika et al. 2015] for the single-interface special case.

So the ramp is really a **three-branch kernel-collapse cascade**, each branch
`r = 0` and unbiased on its own feasibility set:

| branch | feasibility set | operator | `r` | bias |
|---|---|---|---|---|
| 1 connection | rough + visible (`{s=1}`, §5.2) | reconnection shift [Lin 2022] | 0 | unbiased |
| 2 **manifold** | specular chain, root exists + affordable | **manifold reconnection** [SMS / Specular Polynomials] | 0 | unbiased |
| 3 merge | neither — no real root, or solve cost > bias budget | density kernel (§5.1) | `> 0` | `O(r²)`, consistent |

Branch 2 is a **generalized reconnection shift**: it drives `r → 0` *through* the
delta-BSDF vertices the simple shift (branch 1) cannot, by solving the constraint
rather than connecting blindly. It slots into the same GRIS reservoir as another
candidate with its own shift Jacobian (the manifold/half-vector Jacobian of the
specular solve). The §8 per-branch argument extends verbatim: branch 2 is unbiased
on `{solvable specular chain}`, and the biased merge (branch 3) survives only on
the residual where the polynomial system has no real root in the scene (genuinely
unreachable geometry) or the solve is too expensive to afford this frame.

**This is real-time-affordable, not an offline luxury, and there is a Falcor-8
reference.** PSMS-ReSTIR [Hong, Duan, Wang, Yuksel, Zeltner & Lin 2025] = SMS +
tile-based sample-space partitioning (bounds the Newton walk, builds a per-frame
prior) + **ReSTIR spatiotemporal reuse** to amortize the solve cost. It is
implemented as a **Falcor 8.0** module (OSS: `Utah-Graphics-Lab/PSMS-ReSTIR`) —
same engine as this project, and shares authors (Lin, Zeltner) with the ReSTIR PT
port we already build on. Branch 2 is therefore a study-and-integrate target on the
same footing as the DQLin ReSTIR PT port, not a from-scratch research risk.

Caveat: these solve **specular** chains. Rough-glossy "near-specular" is not a
manifold — it stays in branch 1's `s_rough` gradient region where `r` ramps
continuously (§5.2).

### 5.8 Mutations: decorrelating the cell reservoir

Cell-based storage trades per-pixel independence for cross-pixel reuse, which
**correlates** the resampled population and lets a reservoir fill with duplicate
samples (impoverishment). `project_partial_path_cell.md` payoff #1 attacks this
*structurally* — dedup by `initRandomSeed`, the `slot.M` field replacing Lin 2026's
duplication maps. Metropolis mutation is the **alternative (or complementary)
decorrelation mechanism**, and it is the better fit for the regime our cascade
handles worst.

- **Screen-space precedent.** [Sawhney, Lin et al. 2024] interleave
  Metropolis–Hastings mutations as a block inside ReSTIR, mutating each reservoir
  sample against the *same per-pixel target* RIS uses. **Unbiased**, one mutation
  per sample per frame, and it helps most on **glossy materials and hard-to-sample
  lighting** — precisely the `s_rough` gradient region (§5.2) where neither a clean
  connection (branch 1) nor a manifold solve (branch 2) fully applies and the kernel
  is mid-ramp. A mutation step is the natural decorrelator there.
- **The grid gap — open direction.** That work is screen-space (per-pixel target).
  World-space reservoir reuse exists separately [Boissé 2021] but **without
  mutations**. **MCMC mutations on world-space / grid-cell reservoirs are
  unpublished** — and that is exactly our setting. The cell's stored target (cached
  contribution × kernel mass, §6) plays the role of the per-pixel target; an MH
  accept/reject over the cell turns the cache into a **grid-localized Markov chain**.
- **Our shift maps are the mutation proposals.** Branches 1–3 are already
  deterministic mutations without accept/reject: branch 1 ≈ Veach–Guibas
  lens/caustic perturbation; branch 2's manifold solve has an exact Metropolis twin
  in **Manifold Exploration MLT** [Jakob & Marschner 2012] (MEMLT walks the same
  specular manifold SMS solves one-shot). So branch 2 can run as a solve *or* a
  chain. Adding the MH layer reuses the cascade's kernels as proposals — no new
  proposal machinery.
- **Mutation vs. seed-dedup is a design choice, not a conflict.** Seed-dedup removes
  duplicates by construction (cheap, structural); mutation moves duplicates apart
  (handles correlation seed-dedup can't see, e.g. distinct seeds landing on the same
  glossy lobe). They compose: dedup the slot table, then mutate survivors. This also
  revives the 2006 thesis's Metropolis-mutation lineage (`LADDER_PLAN.md` Stage G).

Open: detailed balance under a *cell-shared* target (the target a sample is mutated
against differs from the one it was inserted under — needs the same care as the
GRIS cross-domain MIS in §8), and mutation cost vs. the structural-dedup baseline.

---

## 6. Open proof obligations / risks

- **Jacobian continuity.** The reconnection-shift Jacobian must be the `r → 0`
  limit of the merge-shift Jacobian, or the MIS weights are discontinuous at the
  limit and "connection = limit of merge" breaks. This is the crux of §4.2 and the
  paper-grade obligation. **Sketched in §8** — it holds on the feasibility set and
  fails exactly on its complement, which turns out to *define* §5.2's feasibility
  map rather than being a separate heuristic. Full GRIS-unbiasedness across the
  ramp (not just per-branch consistency) is left open there.
- **The ReSTIR BDPT challenge — does the merge branch even earn its place?**
  [Hedstrom et al. 2025] keep the un-shiftable (specular/caustic) set **unbiased**
  via connection-based *caustic reservoirs* and explicitly call ReSTIR FG biased
  *because* it merges. And §5.7's manifold reconnection (SMS / Specular Polynomials)
  recovers most of the SDS/pure-specular set **unbiased** by solving the chain. So
  the biased merge's honest niche shrinks twice over: it survives only where (a) the
  path can't be connected (branch 1 fails: specular), AND (b) the specular chain has
  no real root in the scene or is too costly to solve this frame (branch 2 fails).
  That residual is genuinely small. The note must scope the merge to it (§5.7, §8)
  and not oversell it as a general fallback; prefer a caustic reservoir for
  connectable caustics and a manifold solve for solvable chains.
- **Target-function choice.** GRIS needs a `p̂` defined on both branches. The
  natural choice is unshadowed path contribution × kernel mass; confirm it keeps
  the support condition (every contributing path reachable) across the ramp.
- **Search-vs-kernel radius interaction.** Decoupling them (§3) is correct but the
  hash must return enough candidates to populate the merge branch where `r` is
  large; tie the cascade-level selection to `r_max`, not to the per-candidate `r`.
- **Temporal photon reuse.** Real-time means photons are regenerated/accumulated
  per frame in the world hash; the `r_min` shrink schedule (§5.4) must be driven by
  the *accumulated* temporal photon count, not per-frame count — with the
  Knaus–Zwicker rate `r_N → 0`, `N·r_N² → ∞` on the SDS-core branch (§8).

---

## 7. Relation to prior work (literature check, 2026-05)

The reservoir × photon-mapping space is more crowded than the original framing
assumed. What is already published:

| work | what it does | what it leaves for us |
|---|---|---|
| **VCM** [Georgiev et al. 2012] | MIS-combines connection + merge per path | offline, per-path MIS, fixed/progressive global radius |
| **ReSTIR FG** [Kern, Brüll, Grosch 2024, EGSR; Falcor, OSS] | reservoir resampling + photon final gather; real-time caustics | **fixed** per-scene kernel, AABB-BVH photons, **no shift maps, no connect+merge** — and **biased due to merging** |
| **ReSTIR BDPT** [Hedstrom, Kettunen, Lin, Wyman, Li 2025, TOG; OSS = the repo we port] | GRIS in **technique-aware extended path space** + **bidirectional hybrid shift** + **unbiased caustic reservoirs** | rejects merging as biased; keeps caustics via connections; notes caustic paths *cannot be spatially shifted* |
| **Differentiable PM / Generalized Path Gradients** [Xing et al. 2024, SA] | merge as a path-sampling technique with a **smooth differentiable kernel** + pdf | exactly our §5.1 kernel requirement, for gradients not for an `r→0` limit |
| **VCM+ / hypothesis-testing kernel** [arXiv 2504.04411, 2025] | per-query kernel radius via an F-test; unbiased under the null | adaptive radius, but **statistical**, not feasibility/shift-driven; offline |
| **Gradient-Domain VCM** [UCSD] | shift mappings applied to photons/merges | shift-on-photons is itself not novel |
| **SMS / Specular Polynomials** [Zeltner 2020; Fan 2024] | **solve** the specular chain between two endpoints (unbiased) | branch 2 (§5.7): recovers SDS the merge would handle biased |
| **PSMS-ReSTIR** [Hong, Duan, Wang, Yuksel, Zeltner, Lin 2025, SA; **Falcor 8.0**, OSS] | SMS + sample-space partitioning + **ReSTIR reuse** for real-time unbiased caustics | branch 2 made real-time — and a Falcor-8 reference to study/integrate directly |

**Now-published — drop from the novelty claim:** reservoir+merge final gather
(ReSTIR FG); GRIS+bidirectional+technique-aware path space+hybrid shift+*unbiased
caustics* (ReSTIR BDPT); per-query adaptive radius (VCM+); smooth merge kernel with
a pdf (Differentiable PM); shift-maps on photons (GD-VCM).

**Still novel after the check:**
1. **One continuous candidate family**, not two techniques. ReSTIR BDPT *separates*
   connection reservoirs from (rejected) merging; ReSTIR FG is merge-only with a
   fixed kernel. We make the reconnection shift a **continuous kernel-collapse
   operator** interpolating merge↔connect *per candidate* inside one GRIS reservoir
   via a nascent-delta family (§5.1, §8). Nobody has the continuous family.
2. **Reconnection feasibility as the radius driver** (roughness × VisCache `μ` ×
   Jacobian bound, §5.2) — geometric and tied to the reservoir's own shift, versus
   VCM+'s statistical F-test or VCM's global schedule. §8 shows this map is not a
   heuristic: it is the indicator of the set on which the `r→0` limit exists.
3. **Three-branch kernel-collapse cascade, correctly scoped merge.** The ramp is
   connection (branch 1) → manifold reconnection (branch 2, §5.7) → biased merge
   (branch 3), each `r=0`/unbiased on its own set. The biased merge survives only on
   the residual that *neither* a connection *nor* a specular-chain solve can reach
   (§5.7, §6, §8). The shifts' job is to *shrink* that biased set toward its minimum.
   Composing a continuous-kernel merge with a manifold-solve branch in one GRIS
   reservoir is itself unpublished.
4. **VisCache as the visibility oracle** for the feasibility test + connection
   shadow ray (§5.5), and the **merge-as-VPL-clamp-replacement** framing (§5.6).

**Builds on:** per-cell partial-path storage (photon payload + replay,
`project_partial_path_cell.md`); reconnection/hybrid shift = the kernel-collapse
operator; VisCache CV+RRR = feasibility/visibility oracle; the multilevel cascade =
candidate-set scoping.

**Sequencing.** The prereq is more mature than first thought: ReSTIR BDPT's
technique-aware path space + bidirectional hybrid shift are **published with open
source — and that source is the very repo we are already porting**
(`project_restir_bdpt_port`, `LADDER_PLAN.md` Stage G). Then: store light subpaths
in the world hash → add the merge branch with a Wendland kernel → wire the
feasibility→radius map → validate the §8 Jacobian-continuity limit on Cornell, and
benchmark the SDS-core merge against a ReSTIR-BDPT-style caustic reservoir to
confirm the merge is only used where connection has zero pdf.

---

## 8. Proof sketch: connection is the `r → 0` limit of the merge

**Goal.** Show that as `r → 0` the merge candidate's *contribution*, *pdf*, and
*shift Jacobian* each converge to the connection candidate's, so the connection is
the continuous limit of one family and may sit in the same GRIS reservoir with MIS
weights defined by continuity. Work in path space with the area-product measure
`dμ = ∏ dA(xᵢ)`.

**Setup.** Eye subpath ends at query vertex `x`; light subpath's last vertex
(stored photon) is `y`. Two ways to close the path:

- **Connection (`r=0`).** Deterministically join `x↔y`:
  `C_con = f_s(x)·G(x,y)·V(x,y)·f_s(y)`, with `G = cosθ_x cosθ_y / ‖x−y‖²`. The
  light vertex is pinned at `y` — a Dirac measure `δ_y` in the gather coordinate.
- **Merge (`r>0`).** Accept `y` within `r` of `x`, weighted by `K_r`:
  `C_mer = f_s(x)·f_s(y)·K_r(‖x⊥ − y⊥‖)`, the kernel acting on the tangent-plane
  displacement, `∫K_r = 1`.

**Step 1 — kernel → Dirac (nascent delta).** Take `K_r(u) = r⁻²·φ(u/r)` with
`φ ≥ 0`, `∫φ = 1`, finite second moment (Gaussian / Epanechnikov / Wendland all
qualify, §5.1). Then for any continuous `g`,
`∫ K_r(‖x⊥−y⊥‖) g(y⊥) dy⊥ → g(x⊥)` as `r→0`, i.e. `K_r → δ` weakly. So the merge
gather operator converges to *evaluation at `x`* — the connection's pin. This is
the classical PPM consistency argument (bias → 0); it handles `C_mer → C_con`. The
new content is Steps 2–3, which carry the **pdf and Jacobian** through the same
limit so GRIS stays valid, not just the estimator mean.

**Step 2 — measure unification.** Express the merge pdf in the *same* area-product
measure as the connection:
`p_mer(x̄) = p_light(y) · K_r(‖x⊥−y⊥‖) · |Jac: tangent-disk → path measure|`.
Because `∫K_r = 1`, the kernel is a **probability density over where the merge
places the connection point**, not an extra weight. As `r→0`,
`p_mer(x̄) dy⊥ → p_light(y)·δ(x⊥−y⊥) = p_con`. Crucially we never form a literal
delta numerically: for every `r>0` both candidates are genuine densities w.r.t. the
*one* measure, so the GRIS support condition (`p̂>0 ⇒ some candidate pdf >0`) holds
along the whole ramp. **This dissolves the BPT-vs-PM measure mismatch** — once the
kernel mass is folded into `p_mer`, connect and merge are densities of the same
measure, and the limit is continuous.

**Step 3 — Jacobian continuity (the crux).** The connection shift's Jacobian
`J_con(x,y)` is the solid-angle↔area conversion (the `G` term + BSDF measure
factor). The merge shift maps the photon to a *displaced* connection point
`x'(u) = x + r·u⊥` in the tangent disk, so
`J_mer^(r)(x̄) = ∫_{‖u‖≤1} J_con(x + r·u⊥, y) · K̃_r(u) du`.
`J_con(·,y)` is continuous in its first argument **wherever the connection is
non-degenerate** — both endpoints rough, `‖x−y‖ > 0`, mutually visible. There, by
dominated convergence with `K_r → δ`,
`J_mer^(r) → J_con(x,y)`, uniformly on the set where `J_con` is bounded and
Lipschitz (rough ⇒ bounded BSDF derivatives; `‖x−y‖ ≥ d_min > 0` ⇒ bounded `G` and
gradient). **The limit fails exactly where `J_con` is unbounded or undefined:**
(i) `‖x−y‖→0` — the VPL near-field singularity (§5.6); (ii) a **specular** vertex
at `x` or `y` — `f_s` is a delta, `J_con` ill-defined; (iii) a **visibility
discontinuity** inside the kernel footprint — `V` jumps across the disk. These
three are precisely the complements of `s_jac`, `s_rough`, `s_vis` in §5.2.

**Therefore the feasibility map `s` is not a heuristic — it is the indicator of the
set on which `J_mer^(r) → J_con` holds.** On `{s = 1}` all three (contribution,
pdf, Jacobian) converge, so the GRIS resampling weight
`w^(r) = m^(r)·p̂^(r)·W^(r) → w_con` by continuity; the connection takes the limit
MIS weight `lim_{r→0} m^(r)` with no special-casing and no second reservoir, and is
**unbiased** at `r = 0`. Off `{s = 1}` the connection's weight is *defined* to be
zero (its contribution/pdf does not exist), the merge carries the path with bias
`O(r²)` (kernel 2nd moment × curvature of `J_con·f`) that vanishes only as the
temporal photon count `→ ∞`, and that residual-bias set is exactly the
SDS/specular/near-field core ReSTIR BDPT also cannot shift.

**Branch 2 (manifold reconnection, §5.7) extends this verbatim.** On
`{specular chain, solvable}` the manifold solve is a deterministic connection
*through* the specular vertices, with its own half-vector/manifold Jacobian; it is
`r=0` and unbiased there (SMS's Bernoulli inverse-probability estimator). So branch 2
removes a sub-region from the off-`{s=1}` complement above — the part where the
specular system has a real root — and the biased merge (branch 3) inherits only the
residual where no root exists or the solve is unaffordable. The same per-branch
limit/Jacobian argument applies to each branch on its own feasibility set.

**Left open (be honest):**
1. **Full GRIS unbiasedness across the ramp**, not just per-branch consistency.
   Step 2 gives the support condition and a common measure; a complete proof must
   write the GRIS contribution weight `W_i` and resampling MIS `m_i` for *all three*
   branches' shift Jacobians and check Lin 2022's proper-pairwise-MIS + domain-
   coverage conditions at every fixed `r`.
2. **Temporal shrink rate** on the SDS-core merge branch: `r_N → 0`, `N·r_N² → ∞`
   (Knaus–Zwicker) for consistency under real-time accumulation. Irrelevant on
   `{s=1}` (already `r = 0`); governs only the fallback core.
