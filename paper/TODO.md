# Paper Revision TODO
**"Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing"**
_Review session March 2026_

---

## Title & Abstract
- [x] **CRITICAL** Rename paper — drop "Multilevel Visibility Cache", use "Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing"
- [ ] Consider "Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing" as alternative — stronger narrative, explicit lineage
- [x] **CRITICAL** Remove "TODO: experimental validation" from abstract — replaced with red ##% placeholders for DI and GI ray reduction
- [ ] Add CV+RRR framing sentence to abstract: _"We exploit the control-variate estimator with Russian roulette — a classical but underutilized technique — to make shadow ray gating provably unbiased regardless of cache accuracy."_
- [ ] Add "revisit" framing to abstract: _"We develop a binary visibility experiment from [Kugelmann 2006] into a complete real-time system..."_

---

## §1 Introduction
- [ ] Reframe contribution list — CV+RRR not claimed as new; application and combination are the contributions
- [ ] Remove "path sharing aligns with ReSTIR" as an architectural insight — this is a generic property of any spatial cache
- [ ] Add "narrowing and deepening" framing: 2006 cached irradiance + visibility jointly; this paper narrows to visibility only (justified by Bernoulli simplification) and deepens with multilevel structure and variance-driven spatial resolution
- [ ] State the three actual contributions explicitly:
  1. Pairwise binary V(A,B) hash with variance-gated multilevel addressing + CV+RRR — development of the 2006 (point, point): bool experiment into a complete real-time system
  2. Three unified ReSTIR integration points (§11.1, §11.2, §11.3) sharing one cache
  3. Adaptive pMin / firefly budget interaction (§10.1)

---

## §2 Related Work
- [ ] Add dedicated paragraph on [Kugelmann 2006]: three separate cache experiments — (1) irradiance (point, dir) → ℝ, (2) binary visibility (point, point) → {0,1}, (3) free-path distance (point, dir) → ℝ≥0 — each with CV+RRR correction rates driven by their respective variances, in a fixed-resolution single-level spatial hash. State that this paper develops experiment (2) into a complete real-time system.
- [ ] Note gap between "known and experimented with" in 2006 and "fully developed" now — hardware and ReSTIR framework are what changed
- [ ] **HIGH** Add Bokšanský & Meister 2025 (JCGT, AMD) — concurrent neural visibility cache; same §11.1 visibility-weighted selection idea, different data structure
- [ ] Add Liu et al. 2025 (SIGGRAPH) — Reservoir Splatting; one sentence, orthogonal problem. Note: splats path reservoirs, NOT visibility estimates — "splatted vis might be wrong" framing was incorrect
- [ ] Add Zhang et al. 2024 (Area ReSTIR) — CV+RRR integrates identically post-shading, no architectural change needed
- [ ] Verify pcg3d citation — [Jarzynski & Olano 2020] is the JCGT hash functions paper; confirm it covers pcg3d specifically

---

## §4 CV+RRR Estimator
- [ ] Give CV+RRR the full derivation treatment even though it is known — show unbiasedness proof clearly
- [ ] Add generality statement: CV+RRR converts any visibility cache (spatial hash, neural network, temporal reprojection) into an unbiased estimator wherever a mean estimate µ is available
- [ ] Drop independent development claim — replace with explicit lineage statement referencing [Kugelmann 2006]
- [ ] **HIGH** Frame as continuation of [Kugelmann 2006] experiment (2): correction-rate mechanism carries over unchanged; two extensions are new: (a) variance now also governs spatial resolution via write-depth gate — absent in 2006 where resolution was fixed; (b) three-level hash replacing single-level
- [ ] **HIGH** State the three motivations for binary over free-path distance (experiment 3 from 2006): sufficient for shadow decisions; Bernoulli structure gives variance for free from µ alone (var = µ(1−µ), no separate estimator needed); (point, point) domain aligns naturally with ReSTIR's pairwise queries
- [ ] Add one sentence on free-path distance experiment from 2006 — richer representation explored but not pursued here; binary is sufficient and cheaper
- [ ] Make coupled variance adaptation explicit: same variance signal drives both RR survival probability p (correction rate) and write-depth gate (spatial resolution) — self-regulating property that makes the system practical without per-scene tuning
- [ ] Cross-reference §4 coupling from §7 write-depth gate section

---

## §5 Hash Structure
- [ ] Add calibration note after Table 1: state scene scale and viewing distance assumptions ("calibrated for primary viewing distances of 2–20 m, exterior/interior mixed scenes")
- [ ] Consider reframing Table 1 cell sizes as pixel counts rather than world-space distances — makes values scene-independent and reviewable (8 cm ≈ 8.6 px, 62 cm ≈ 67 px at 90°/1080p/5 m)
- [ ] Add explicit vs. neural tradeoff paragraph — inspectable, zero inference overhead, predictable cold-start vs. MLP latency and training convergence
- [ ] Explain LOD asymmetry (A finer than B) — justified for DI (B = light), but acknowledge GI revalidation (B = surface) may warrant symmetric cells

---

## §6 Addressing / §8 Decay
- [ ] ABA race dismissed as "wastes traced sample" — quantify error rate or fix with proper CAS; do not dismiss without data
- [ ] Add DECAY_PERIOD half-life math — show arithmetic for 15 frames and 300 frames to make values non-arbitrary
- [ ] Add one sentence on camera-adaptive cell sizing (FoV + CoC) as future work

---

## §10 Firefly / §11 ReSTIR Integration
- [ ] **HIGH** §10.1: Clarify firefly_budget units — "contribution / firefly_budget" normalization is underspecified
- [ ] **HIGH** §11.1: Define M in "1/M of budget" — M is undefined in current draft
- [ ] **HIGH** §11.1: Add Bokšanský & Meister 2025 citation — same visibility-weighted WRS idea
- [ ] §11.1: Add unbiasedness argument explicitly — µ_min floor guarantees every light has nonzero selection probability, preserving RIS support coverage; unlike neural DI biased mode

---

## §13 / §15 Results & Ablation
- [ ] **CRITICAL** §13 Table 4: "~60% benefit at ~5% cost" has no supporting data — add measurements or mark clearly as projected
- [ ] **CRITICAL** §15 Results is entirely TODO — add at minimum one informal Bistro profiling data point before submission
- [ ] Add multilevel vs. finest-level-only to ablation table — tests the architectural claim directly; implement via minLevel/maxLevel params
- [ ] Add disocclusion stress test: fast camera flythrough, measure frames to 80% hit rate post-disocclusion and variance spike duration
- [ ] Ablation −B (variance gate off) is the most important internal test — must show negligible MSE gain at measurable insert cost increase; if not, raise VAR_THR before submission
