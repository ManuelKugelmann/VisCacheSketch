# 2. Related Work

## 2.1 Foundation: Kugelmann [2006]

This paper builds directly on [Kugelmann 2006],
a thesis on adaptive global illumination that developed a general framework
called *predictions with correction at random* (Sec. 3.4 of the thesis) —
using a cached prediction as control variate
and Russian roulette to decide whether to correct,
with generalized variance (tracked explicitly per cache entry)
driving adaptive sampling (Sec. 3.4.1).
The framework was applied through many explorative cache experiments —
visibility prediction (Sec. 3.2.2),
contribution prediction (Sec. 3.2.3), and others,
using spatial grids for grouping nearby samples —
the grids were visible in the thesis results,
but the underlying use of spatial hashing [Teschner et al. 2003]
to map cells to memory was an unmentioned implementation detail.
The test case was Robust Instant Global Illumination [Keller 1997],
but the caching method itself was always algorithm-agnostic —
it operates on pairwise queries
regardless of the rendering algorithm generating them.
The visibility prediction component is the direct ancestor of this work.
The thesis was broader
(visibility + contribution prediction, unbiased light cuts,
adaptive global illumination)
but shallower in each area:
fixed-resolution spatial grids,
variance driving only the correction rate, CPU-only implementation.
We narrow to binary visibility and deepen it
with improvements from subsequent work:
formal spatial hashing [Teschner et al. 2003] with robust addressing
(modifying [Binder et al. 2018], hash quality from [Jarzynski & Olano 2020]),
fingerprint-based collision handling ([Binder et al. 2018])
with GPU-parallel lock-free updates ([Gautron 2021]),
LOD level encoded in the hash key ([Gautron 2020]),
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

Teschner et al. [2003] established spatial hashing
for collision detection of deformable objects:
an infinite regular grid compressed to a finite table via hash function,
requiring no scene bounds.
This was encountered during teaching assistant work
on Keller's simulation algorithms lectures at Universität Ulm,
where it was used for broad-phase physical collision detection.
The motivation for adopting spatial hashing came from
Keller's lecture hints that all naive spatial grids
are doomed by the curse of dimensionality —
and trees also suffer from it to some degree.
Spatial hashing sidesteps this by compressing
the sparse occupancy of a high-dimensional grid into a compact table.
This was the pedagogical root of applying spatial hashing
to illumination caching in [Kugelmann 2006]
and subsequent GPU hash table work.

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
multiple resolutions in one flat table, distance-gated selection.
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
on RR termination.
Szirmay-Kalos, Antal and Sbert [2005] extended it
into a variance-driven splitting/RR framework
("go with the winners" for path tracing),
using a scene-global average radiance estimate
(from total emitted power and average albedo) on termination.

Kugelmann [2006] arrived at the same CV+RR math independently
as *predictions with correction at random* (thesis Sec. 3.4),
but with two refinements that make the technique practical:
(a) the **estimation source** is a per-point spatial cache
rather than a scene-global constant —
a good local prediction gives near-zero residual variance,
while a global average helps little;
(b) **generalized variance** (tracked explicitly per cache entry)
drives the RR survival probability as adaptive sampling (Sec. 3.4.1),
closing the loop between cache quality and trace rate.
The thesis explored many cached quantities through explorative experiments —
visibility, contribution, and others —
all using general variance estimators.
By narrowing to binary visibility, we exploit Bernoulli structure:
var = μ(1−μ) is free from the mean alone,
eliminating the separate variance accumulator.
We do not claim the CV+RR math as a contribution —
it is common technique.
What we add is a second use of the same variance signal:
write-depth gating (Sec. 5) drives spatial resolution
in addition to correction rate,
creating a self-regulating loop
that only becomes possible with a multilevel cache.

## 2.5 Integration Targets (Orthogonal)

The visibility cache is agnostic to the algorithm
that generates visibility queries.
We demonstrate integration with ReSTIR
[Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022]
and note compatibility with Area ReSTIR [Zhang et al. 2024]
and Reservoir Splatting [Liu et al. 2025],
but these are *integration targets*,
not related work in the visibility caching sense.
The same cache applies equally to instant radiosity
(as in [Kugelmann 2006]),
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
