# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

A flat, multilevel spatial hash table (8-byte entries, lock-free atomics)
caches binary visibility predictions in world space
and corrects them stochastically to keep the estimator unbiased.
Demonstrated with ReSTIR DI/GI on Bistro exterior:
**##%** fewer shadow rays (direct), **##%** (GI revalidation),
no measurable bias.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling
