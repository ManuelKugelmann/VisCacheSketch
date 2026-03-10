# 14. Conclusion

We have described an assembly of known techniques for real-time visibility caching: sparse multilevel hash replacing NEE++'s dense matrix [Guo et al. 2020], control-variate RR [Szirmay-Kalos et al.] returning cached mean on trace termination, distance-gated LOD intervals, angular quantization for infinite endpoints, runtime statistics with auto-tuning, and integration with ReSTIR DI/GI pipelines.

Key observations: (1) ReSTIR GI's selection concentration aligns with coarse cache cells, enabling within-frame amortization of revalidation traces; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing.
