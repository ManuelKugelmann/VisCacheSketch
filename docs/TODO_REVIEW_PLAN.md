# TODO Review & Action Plan
_Review date: March 2026_

This document reviews all TODOs across the project and classifies them as
**apply now**, **defer**, or **remove (outdated)**.

---

## Sources reviewed

| File | Items | Nature |
|------|-------|--------|
| `TODO.md` | ~50 | Master tracker (implementation + paper) |
| `paper/TODO.md` | ~35 | Detailed paper revision items |
| `paper/CITATIONS.md` | 6 | Citation integration plan |
| Source code (13 inline TODOs) | 13 | Shader/C++ placeholders |
| `docs/DESIGN.md` | 1 | ABA race note |

---

## Classification

### REMOVE (outdated or already done)

| TODO | Reason |
|------|--------|
| "Consider alternative title: Revisiting Visibility..." (`TODO.md` S3.3, `paper/TODO.md`) | Title was already decided and renamed (marked `[x]`). `RESEARCH_NOTES.md` shows the decision is pending between two candidates. **Action:** make a final title decision and remove the TODO. |
| "Test setup.sh end-to-end on clean clone" (`TODO.md` S1.3) | CI already runs `setup.sh` on clean runners (`ubuntu-22.04`, `windows-2022`). Replace with "verify CI is green" which is a standing practice, not a TODO. |
| "Add Linux/Mac build notes" (`TODO.md` S1.3) | Linux builds work in CI. Mac is not targeted. Change to a one-line note in README: "Windows + Linux supported; macOS untested." |
| 6-week build sequence table (`TODO.md` S5) | Timeline is stale. Week 1 is done, weeks 2-6 are all "pending" with no dates. Either re-baseline with real dates or remove. |
| `paper/CITATIONS.md` items for Muller 2022, Lin 2022, Stotko 2025 | These say "Already cited. No new text needed." They are tracking items, not action items. Remove once confirmed in the paper. |

### DEFER (future work / blocked, keep but deprioritize)

| TODO | Reason |
|------|--------|
| Camera-adaptive cell sizing via FoV/CoC (`TODO.md` S1.4, `VisCache.slang:167`) | Explicitly marked "future work" in code and paper. Keep as-is. |
| Cell sizes at non-standard scene scales (`TODO.md` S1.4) | Requires empirical testing on varied scenes. Defer until post-submission. |
| Symmetric cells for GI revalidation (`TODO.md` S1.4) | "Measure error before changing constants." Blocked by DQLin port. |
| Free-path distance experiment (from 2006) | Explicitly scoped out of this paper. Keep as future work note. |
| Full ablation sweep items `-A` through `-E`, stress tests (`TODO.md` S2) | All blocked by DQLin port. Valid but cannot be acted on now. |
| 1024 spp reference capture, per-pixel MSE, GPU timestamps (`TODO.md` S2.3) | Same -- blocked by running renderer. |

### APPLY NOW -- Paper revision items (no code dependency)

These are purely editorial and can be done in the paper draft immediately:

**CRITICAL (blocks submission):**

| TODO | Action |
|------|--------|
| Remove "TODO: experimental validation" from abstract | Edit abstract. Can be done now with placeholder wording; finalize after results. |
| S13 Table 4 "~60% benefit at ~5% cost" -- mark as projected | If no data exists, add "(projected)" annotation. Honest framing. |
| S15 Results is entirely TODO | Write a skeleton results section with the metrics structure. Fill numbers later. |

**HIGH (significant gaps, no code needed):**

| TODO | Action |
|------|--------|
| Add Boksansky & Meister 2025 citation (S2, S4, S11.1) | Full text is already drafted in `CITATIONS.md`. Copy into paper. |
| Add Liu et al. 2025 one sentence (S2) | Text drafted in `CITATIONS.md`. |
| Add Zhang et al. 2024 one sentence (S2) | Text drafted in `CITATIONS.md`. |
| Clarify firefly_budget units (S10.1) | Define units explicitly in text. |
| Define M in "1/M of budget" (S11.1) | Add definition. |
| Frame S4 as continuation of Kugelmann 2006 experiment (2) | Rewrite per `RESEARCH_NOTES.md` framing. |
| State three motivations for binary over free-path (S4) | Listed in `paper/TODO.md`. Write into S4. |
| Add Kugelmann 2006 lineage paragraph to S2 | Text direction in `CITATIONS.md` and `RESEARCH_NOTES.md`. |

**NORMAL (polish, can be done anytime before submission):**

| TODO | Action |
|------|--------|
| Add CV+RRR framing sentence to abstract | One sentence addition. |
| Add "revisit" framing to abstract | One sentence. |
| Reframe contribution list in S1 | Per `paper/TODO.md` guidance. |
| Remove "path sharing aligns with ReSTIR" from S1 | Delete sentence. |
| Add "narrowing and deepening" framing to S1 | Per `RESEARCH_NOTES.md`. |
| State three actual contributions explicitly (S1) | Listed in `paper/TODO.md`. |
| Full unbiasedness derivation for CV+RRR (S4) | Mathematical writeup. |
| CV+RRR generality statement (S4) | One paragraph. |
| Drop independent development claim in S4 | Edit existing text. |
| Make coupled variance adaptation explicit (S4) | Per `RESEARCH_NOTES.md` -- key novelty claim. |
| Cross-reference S4 coupling from S7 | Add forward ref. |
| Add calibration note after Table 1 (S5) | One sentence. |
| Consider pixel-count reframing of cell sizes (S5) | Optional editorial improvement. |
| Add explicit vs. neural tradeoff paragraph (S5) | One paragraph. |
| Explain LOD asymmetry A finer than B (S5) | Per `RESEARCH_NOTES.md`. |
| ABA race -- quantify or fix with CAS (S6) | Write honest assessment. Can note expected error rate ~3% from RESEARCH_NOTES. |
| Add DECAY_PERIOD half-life math (S8) | Arithmetic for 15 and 300 frames. |
| Camera-adaptive cell sizing as future work sentence (S6) | One sentence. |
| S11.1 unbiasedness argument (mu_min floor) | One paragraph. |
| Verify pcg3d citation | Confirm Jarzynski & Olano 2020 covers pcg3d. |
| Multilevel vs finest-only ablation row in table | Add row structure now, fill data later. |

### APPLY NOW -- Code items (no DQLin dependency)

| TODO | Action |
|------|--------|
| ABA race quantification (`docs/DESIGN.md`, `TODO.md` S1.4) | Can add a comment in `VisCache.slang` with the ~3% estimate from RESEARCH_NOTES, or implement 64-bit CAS. |

### BLOCKED -- Code items (require DQLin port)

| TODO | Notes |
|------|-------|
| Port DQLin/ReSTIR_PT into Falcor fork | THE critical path blocker. All 12 ReSTIRGI shader TODOs resolve when this is done. |
| Verify ported pass matches DQLin reference (FLIP < 0.01) | After port. |
| Verify traces/pixel baselines (5.0 and 0.5-1.0) | After port. |
| Run Bistro profiling data point | After port. Unblocks results section. |

---

## Recommended execution order

### Phase 1: Paper text (no blockers, do now)
- Fix CRITICAL abstract/results placeholders
- Add three new citations (text already drafted)
- Fix undefined terms
- Kugelmann 2006 lineage framing (HIGH)
- Remaining polish items in section order

### Phase 2: DQLin port (the single code blocker)
- Port DQLin/ReSTIR_PT to Falcor 8.0
- Verify against reference images
- Baseline traces/pixel metrics

### Phase 3: First results (unblocks submission)
- Run one Bistro profiling data point
- Update Table 4 and results section with real numbers
- ABA race: measure empirically now that renderer works

### Phase 4: Ablation & validation
- Run key ablations (variance gate off, multilevel vs finest)
- Capture references, compute MSE

### Phase 5: Cleanup
- Remove outdated TODOs
- Update `TODO.md` to reflect completed items

---

## Duplicate tracking

`TODO.md` S3 and `paper/TODO.md` have significant overlap. After this plan is
executed, consolidate: keep `paper/TODO.md` as the detailed paper checklist and
make `TODO.md` S3 a summary with a pointer to `paper/TODO.md`.
