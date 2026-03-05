# Paper Revision TODO
**"Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing"**
_Review session March 2026_

---

## Title & Abstract
- [x] **CRITICAL** Rename paper — drop "Multilevel Visibility Cache", use "Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing"
- [ ] Consider "Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing" as alternative — stronger narrative, explicit lineage
- [x] **CRITICAL** Remove "TODO: experimental validation" from abstract — replaced with red ##% placeholders for DI and GI ray reduction
- [x] Add CV+RRR framing sentence to abstract — integrated into existing control-variate sentence with unbiasedness guarantee
- [x] ~~Add "revisit" framing to abstract~~ — removed; 2006 lineage belongs in §1/§2, not abstract

---

## §1 Introduction
- [x] Reframe contribution list — CV+RRR explicitly not claimed as new; advocate for wider adoption
- [x] Remove "path sharing aligns with ReSTIR" — replaced with general world-space cache + ReSTIR synergy observation
- [x] Add 2006 lineage: three independent experiments, we develop binary visibility into complete system
- [x] State three contributions: (1) real-time binary V cache with self-regulating CV+RRR, (2) three ReSTIR integration points sharing one cache, (3) capacity management + optional multilevel for cell-size robustness

---

## §2 Related Work
- [x] Add dedicated paragraph on [Kugelmann 2006] — three experiments, binary visibility as direct ancestor, hardware gap
- [x] Note gap between 2006 and 2026 — GPU ray tracing, wave intrinsics, ReSTIR
- [x] **HIGH** Add Bokšanský & Meister 2025 — concurrent neural cache, visibility-weighted selection, biased default mode
- [x] Add Liu et al. 2025 (Reservoir Splatting) — one sentence, orthogonal, corrected framing
- [x] Add Zhang et al. 2024 (Area ReSTIR) — CV+RRR integrates without modification
- [x] Verify pcg3d citation — confirmed [Jarzynski & Olano 2020, JCGT 9(3)] covers pcg3d specifically; added to §2

---

## §4 CV+RRR Estimator
- [x] Full unbiasedness derivation with residual variance formula
- [x] Generality statement — applies to any cache providing mean estimate µ
- [x] Drop independent development claim — explicit 2006 lineage in §1 and §2
- [x] **HIGH** Frame as continuation of 2006 experiment (2) with two new extensions
- [x] **HIGH** Three motivations for binary over free-path distance
- [x] Free-path distance noted as richer but not pursued
- [x] Coupled variance adaptation — dedicated paragraph, key architectural property
- [x] Cross-reference from §5 write-depth gate back to §8 coupled variance adaptation

---

## §5 Hash Structure
- [x] Calibration note after Table 1 — 2–20 m viewing distances, Bistro/Sponza
- [x] Pixel-count column added to Table 1 with footnote on distance gating
- [x] Explicit vs. neural tradeoff paragraph
- [x] LOD asymmetry explanation — justified for DI, symmetric deferred for GI

---

## §6 Addressing / §8 Decay
- [x] ABA race quantified — ~3% at L2 without warp reduction, negligible at L0; 64-bit CAS noted as alternative
- [x] DECAY_PERIOD half-life math — arithmetic for 60 and 300 frames
- [x] Camera-adaptive cell sizing noted as future work in calibration paragraph

---

## §10 Firefly / §11 ReSTIR Integration
- [x] **HIGH** §10.1: firefly_budget defined as max tolerable absolute luminance (cd/m²) with worked example
- [x] **HIGH** §11.1: M defined as number of initial light candidates per pixel (typically 32)
- [x] **HIGH** §11.1: Bokšanský & Meister 2025 citation added
- [x] §11.1: Unbiasedness argument — µ_min floor + exploration candidate prevent permanent exclusion

---

## §13 / §15 Results & Ablation
- [x] **CRITICAL** §13 Table 4: marked as "(projected)" with red placeholder for measured comparisons
- [x] **CRITICAL** §15 Results: replaced TODOs with structured red skeleton (13.1–13.5) with metric structure
- [ ] Add multilevel vs. finest-level-only to ablation table — tests the architectural claim directly; implement via minLevel/maxLevel params (included in skeleton)
- [ ] Add disocclusion stress test: fast camera flythrough, measure frames to 80% hit rate post-disocclusion and variance spike duration
- [ ] Ablation −B (variance gate off) is the most important internal test — must show negligible MSE gain at measurable insert cost increase; if not, raise VAR_THR before submission
