/***************************************************************************
 # ReSTIRCommon.cpp — no-op plugin shell for ReSTIR-DI-lineage shared slang.
 #
 # Registers no render-pass class. Exists purely to build + deploy the
 # shared slang module under `runtime/shaders/RenderPasses/ReSTIRCommon/`,
 # from where ReSTIR DI plugins import it as
 # `RenderPasses.ReSTIRCommon.LightReservoir`.
 #
 # Contains the DI-lineage LightSampleDI struct + light-sample rebuilders.
 # Truly-common path-tracing primitives (LightSample base, ILightSampleBase
 # interface, MIS/RR/selection) live in the PathTraceCore plugin.
 *************************************************************************/
#include "Falcor.h"
#include "Core/Plugin.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    // Intentionally empty — ReSTIRCommon deploys shared slang utilities only.
}
