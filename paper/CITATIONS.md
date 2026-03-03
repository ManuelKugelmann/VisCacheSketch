# Citation Integration Plan
_6 additions to current draft_

---

## New citations

### Bokšanský & Meister 2025 (AMD, JCGT)
**"Neural Visibility Cache for Real-Time Light Sampling"**

**Relation:** Concurrent work. Same §11.1 idea — visibility-weighted WRS for DI candidate selection — but using a neural hash grid (instant-ngp backbone) instead of a spatial hash. Their default mode is biased: uses network output directly for shading, skipping shadow rays when confident. CV+RRR could make it unbiased — worth noting as a unifying observation.

**Where to cite:**
- §2 Related Work: one paragraph, note concurrent timing and different data structure
- §4 after generality statement: "Bokšanský and Meister [2025] apply a neural variant; CV+RRR would make their biased mode unbiased by construction"
- §11.1: explicit citation at visibility-weighted selection point

**Framing for §2:**
> "Concurrent with this work, Bokšanský and Meister [2025] feed neural visibility estimates into WRS for light selection; we apply the analogous idea within ReSTIR candidate generation using spatial hash lookups. Unlike using cached visibility directly for shading — which introduces bias when the cache is wrong — visibility-weighted selection with µ_min floor preserves unbiasedness: every light remains selectable regardless of cache accuracy."

**To confirm:** does their paper include a debiasing option? If not, the CV+RRR observation is a discussion contribution.

---

### Liu et al. 2025 (NVIDIA, SIGGRAPH)
**"Reservoir Splatting for Temporal Path Resampling and Motion Blur"**

**Relation:** Orthogonal. Addresses temporal reuse robustness under camera motion via forward-projected primary hits + Jacobian correction. Splats **path reservoirs**, NOT visibility estimates. The earlier framing "splatted visibility might be wrong" was incorrect — retract everywhere.

**Where to cite:**
- §2: one sentence, orthogonal problem statement

**Framing for §2:**
> "Reservoir Splatting [Liu et al. 2025] improves temporal path reuse robustness under camera motion via forward projection with Jacobian correction; our cache addresses the orthogonal problem of spatial revalidation cost."

---

## Recontextualised existing citations

### Zhang et al. 2024 (SIGGRAPH) — Area ReSTIR
**Relation:** Orthogonal. Extends ReSTIR DI to lens×light area sampling for DOF/AA. Final shadow ray structure identical to standard RTXDI — CV+RRR applies at the same post-shading point without modification.

**Action:** Add one sentence in §2: "CV+RRR integrates with Area ReSTIR [Zhang et al. 2024] without modification: the final shadow ray structure is identical to standard RTXDI." Use as modern DI baseline in experiments (Falcor 8.0 native).

---

### Müller et al. 2022 (instant-ngp)
**Relation:** Hash grid backbone used by Bokšanský & Meister 2025. Keller co-author connects neural approach to spatial hashing lineage.

**Action:** Already in §2. No new text needed beyond the Bokšanský & Meister discussion.

---

### Lin et al. 2022 (GRIS / ReSTIR_PT)
**Relation:** Essential baseline for §11.3 Table 3 ground truth. DQLin/ReSTIR_PT is the fork to port to Falcor 8.0.

**Action:** Already cited. Ensure the port is complete before claiming Table 3 numbers. Cannot publish §11.3 without this baseline.

---

### Stotko et al. 2025 (MrHash)
**Relation:** Variance-driven hash adaptation — directly related to §7 variance-gated write depth. Strengthens narrative.

**Action:** Already in §2. No new text needed; cross-reference from §7 write-depth gate.

---

## Text additions by section

### §2 — two new paragraphs
1. [Kugelmann 2006] lineage paragraph — three experiments, correction-rate mechanism, fixed-resolution hash
2. [Bokšanský & Meister 2025] + [Liu et al. 2025] — concurrent and orthogonal work respectively

### §4 — one new paragraph after derivation
Generality statement + Bokšanský & Meister 2025 as concrete example of the principle applied with a different data structure.

### §5.2 — calibration note + explicit vs. neural paragraph
After Table 1: scene scale assumptions. New paragraph: inspectable/tunable/zero-latency vs. neural automatic adaptation.

### §6 — one sentence
Camera-adaptive cell sizing as future work.

### §11.1 — one new paragraph
Unbiasedness of visibility-weighted selection with µ_min floor. Cite Bokšanský & Meister 2025 as concurrent approach that lacks this guarantee in default mode.

### §15 — new ablation row + paragraph
Multilevel vs. finest-only comparison validating architectural necessity of coarse levels for GI path-sharing amortization.
