/***************************************************************************
 # PathTracerX/NRDHelpers.slang
 # Thin stub: re-exports the generic NRD-buffer writers from
 # `RenderPasses.PathTraceCommon.NRDHelpers`. Call sites invoke them with
 # PathState as the generic type argument; Slang's IPathStateNRD-conformance
 # extension in PathState.slang makes the dispatch work.
 *************************************************************************/
__exported import RenderPasses.PathTraceCommon.NRDHelpers;
