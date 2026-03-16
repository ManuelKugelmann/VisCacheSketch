# 2. Related Work

## 2.1 Prediction-with-Correction for Visibility

[Kugelmann 2006] cached pairwise visibility in spatial hash grids
and corrected predictions via variance-driven Russian roulette
(control variate on the residual),
demonstrating the concept on instant radiosity at CPU speeds.
That work used fixed-resolution grids and single-level hashing.
We narrow to binary visibility and deepen the hashing:
robust addressing (modifying [Binder et al. 2018],
hash quality from [Jarzynski & Olano 2020]),
fingerprint-based collision handling
with GPU-parallel lock-free updates [Gautron 2021],
LOD level encoded in the hash key [Gautron 2020],
and variance-driven spatial resolution
(independently paralleled by [Stotko et al. 2025]).

## 2.2 Visibility Caching

Ward [1991] first observed that shadow-ray decisions
can be guided by spatial statistics —
sorting lights by potential contribution
and estimating visibility for below-threshold sources rather than tracing.
This is the conceptual ancestor of all visibility caching:
don't trace shadow rays you can predict.

Popov et al. [2013] developed adaptive quantization visibility caching,
adapting resolution to local visibility complexity via octree subdivision,
reporting less than 2% of shadow rays needed.
Their adaptive-resolution idea is related to our variance-gated write depth,
but uses explicit octree subdivision rather than hash-level selection.
Ulbrich et al. [2013] proposed progressive refinement of cached visibility,
sharing our philosophy that cache quality improves over frames.
Both are offline, CPU-based.

Guo, Eisemann and Eisemann [2020] (NEE++) cache voxel-to-voxel
visibility probability in a 6D domain
with bidirectional symmetry and standard RR rejection,
reporting 80% shadow ray reduction.
Their dense D³×D³ matrix (16³ voxels, ~32 MB, single resolution)
does not scale to large scenes.
Our approach improves on NEE++ in three specific ways:
(a) sparse multilevel hash instead of dense matrix;
(b) prediction-with-correction instead of standard RR —
returning μ on termination rather than zero reduces residual variance;
(c) real-time GPU implementation.

Concurrent with this work, Bokšanský and Meister [2025]
feed neural visibility estimates (Instant-NGP backbone [Müller et al. 2022])
into weighted reservoir sampling for light selection —
the same visibility-weighted selection idea as our Sec. 9.1.
Their primary mode is unbiased
(clamping zero/negative estimates to small positive constants);
a secondary "Neural Direct Illumination" mode
uses network output directly for shading, trading bias for speed.
Prediction-with-correction (Sec. 8) applies identically
to any data structure that provides a mean visibility estimate μ —
it would provide an alternative unbiased path for their neural cache.

## 2.3 Spatial Hashing

Teschner et al. [2003] established spatial hashing:
an infinite regular grid compressed to a finite table via hash function,
requiring no scene bounds.
The practical inspiration for using spatial hashing in [Kugelmann 2006]
came from ODE (Open Dynamics Engine) [Smith 2001],
whose `dHashSpace` broad-phase collision detection
demonstrated spatial hashing as a lightweight, bounds-free spatial index —
encountered through a student project at Universität Ulm.

Binder et al. [2018] applied spatial hashing to path-space filtering
with jitter before quantization,
fingerprint-based collision detection, and linear probing.
We adopt their jitter-before-quantize scheme
and fingerprint collision detection but make two changes:
(1) we replace linear probing with double hashing
using the fingerprint as h2
(better distribution under high load);
(2) we change the jitter seed
from the preliminary cell index to the unquantized position bits.
Binder's cell-index seed means all positions in one cell
share the same jitter,
producing sharp, persistent boundary steps — a systematic bias.
Position-seeded jitter gives each surface point independent jitter,
converting boundary artifacts from irreducible bias into reducible variance —
the standard Monte Carlo trade-off.
The jitter is not merely noise;
it acts as an intrinsic box filter across cell boundaries (Sec. 4).

Gautron [2020, 2021] demonstrated LOD level encoded directly
in the hash function for real-time ray-traced AO,
with viewing-distance-based cell size selection.
We adopt this design:
level index in the hash key,
multiple resolutions in one flat table, variance-gated cascade (Sec. 5).
Prior multilevel hash approaches —
separate tables per level [Müller et al. 2022],
octree-like hierarchical indirection, dense multi-resolution grids —
were all more complex for our use case and performed worse.
The flat-table approach is simple, has no indirection overhead,
and the LOD-in-key design means entries at different levels
can coexist and be evicted independently.

Stotko et al. [2025] (MrHash) independently developed
variance-driven resolution adaptation in a flat hash for TSDF reconstruction —
the same principle as our variance-gated write depth,
applied to a different domain.

SHaRC [Benyoub et al. 2024] (Spatial Hash Radiance Cache),
shipped in NVIDIA's RTX SDK,
uses world-space spatial hashing with two-pass update (sparse update + query)
and roughness-gated LOD selection.
Their LOD gating by surface roughness —
coarse cells for glossy surfaces, fine cells for sharp reflections —
is complementary to our variance-gated write depth:
roughness gates the *query* resolution,
variance gates the *write* resolution.
SHaRC does not use a variance-coupled write gate,
which is the mechanism that makes our cache self-regulating (Sec. 5).

For hash noise we use pcg3d [Jarzynski and Olano 2020],
a GPU hash function that passes all but one BigCrush test
at ~12 ALU with no lookup table.

## 2.4 Prediction-with-Correction (Adaptive Sampling)

Using a control variate instead of zero on Russian roulette termination
is standard Monte Carlo variance reduction —
combining two textbook techniques
[Knuth 1973; Hammersley and Handscomb 1964].
The idea is at least implicit in the "go with the winners" family
(Aldous and Vazirani [1994]; Grassberger [2002]):
when terminating a path,
substitute an estimate of the remaining contribution
rather than discarding it.
In the graphics context,
Szécsi, Szirmay-Kalos and Kelemen [2003] formalized this for rendering,
showing the variance benefit of returning a non-zero estimate
on RR termination — but with fixed RR probability,
not variance-driven.
Szirmay-Kalos, Antal and Sbert [2005] added variance-driven RR
via a splitting/RR framework ("go with the winners" for path tracing),
using a scene-global average radiance estimate
(from total emitted power and average albedo) on termination.

[Kugelmann 2006] refined the estimation source
to a per-point spatial cache (rather than a scene-global constant)
and used variance to drive RR survival probability,
closing the loop between cache quality and trace rate.
By narrowing to binary visibility, we exploit Bernoulli structure:
var = μ(1−μ) is free from the mean alone,
requiring no separate accumulator.
What we add is a second use of the same variance signal:
write-depth gating (Sec. 5) drives spatial resolution
in addition to correction rate,
creating a self-regulating loop
that only becomes possible with a multilevel cache.

Bolin and Meyer [1997] first analyzed optimal RR/splitting factors
from variance estimates per bounce level.
Vorba and Křivánek [2016] (ADRRS) precompute an adjoint importance function
to set per-scattering-event weight windows —
RR where importance is low, splitting where it is high.
Rath et al. [2022] (EARS) learn optimal RR/splitting factors
during rendering via efficiency-aware iteration,
provably converging to Bolin and Meyer's optimal factors;
Meyer et al. [2024] (MARS) generalize this to per-technique sample counts.
All operate on **path continuation** decisions (bounce-level RR/splitting),
not on shadow ray gating.
Our work is orthogonal:
we use variance-driven RR to gate individual shadow rays
against a cached control variate,
not to decide whether a path should survive another bounce.
The connection is that both families
allocate sampling budget from a variance or importance signal —
ADRRS's p_lim (adjoint-weighted survival floor)
is formally analogous to our contribution-weighted pfloor (Sec. 8.1),
and ADRRS's coupling of one signal to one decision (path continuation)
maps onto our coupling of one signal to two decisions —
correction rate and write depth — as detailed in Sec. 8.

Sanzharov et al. [2025] (Neural Two-Level Monte Carlo)
use a neural incident radiance cache
in a Two-Level Monte Carlo scheme
to compensate for cache bias,
introducing a Balanced Termination Heuristic (BTH)
that decides when to trust the cache vs. trace further.
Their BTH is structurally a stochastic version
of our variance-gated write depth (Sec. 5):
both decide at which level to stop and trust the cache.
Our variance-coupled correction rate (Sec. 8)
maps directly onto the MLMC residual estimator structure —
the control variate returns the cached prediction,
the residual corrects it stochastically.
Their use of world-space multi-level hash encodings
further parallels our LOD-in-key design (Sec. 4).
The key difference is the domain:
they cache radiance (continuous, high-dimensional),
we cache binary visibility (Bernoulli, variance-free from mean).

## 2.5 Integration Targets (Orthogonal)

Our implementation is built on Falcor [Kallweit et al. 2022],
NVIDIA's open-source real-time rendering research framework,
which provides the GPU infrastructure, scene management,
and render-graph architecture used by our render passes.

The visibility cache is agnostic to the algorithm
that generates visibility queries.
We demonstrate integration with ReSTIR
[Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022]
and note compatibility with Area ReSTIR [Zhang et al. 2024]
and Reservoir Splatting [Liu et al. 2025],
but these are *integration targets*,
not related work in the visibility caching sense.
The same cache applies equally to instant radiosity,
classical path tracing with next-event estimation,
or any algorithm evaluating pairwise visibility.
ReSTIR is a particularly good fit because spatial reuse
concentrates many pixels onto shared light/secondary-hit pairs,
naturally amortizing cache lookups —
but this is a property of the integration, not of the cache.

ReSTIR DI [Bitterli et al. 2020] introduced
resampled importance sampling for direct lighting.
Ouyang et al. [2021] and Lin et al. [2022] extended this to path reuse,
where revalidation rays test visibility
from the current shading point to a neighbor's secondary hit.
The biased/unbiased tradeoff —
skip revalidation (light leaks) vs. always retrace (expensive) —
is what makes GI revalidation our strongest integration case (Sec. 9.3).
Prediction-with-correction resolves this tradeoff:
unbiased revalidation at near-biased-skip cost.
