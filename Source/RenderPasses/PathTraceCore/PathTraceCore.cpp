/***************************************************************************
 # PathTraceCore.cpp — no-op plugin shell for truly-common slang utilities.
 #
 # Registers no render-pass class. Exists purely to build + deploy the
 # shared slang module under `runtime/shaders/RenderPasses/PathTraceCore/`,
 # from where other plugins import it as
 # `RenderPasses.PathTraceCore.PathTraceCore`.
 #
 # Companion plugin `ReSTIRCommon` hosts DI-lineage extensions
 # (LightSampleDI, rebuilders). PT-lineage extensions would land in a
 # future `ReSTIRPTCommon` plugin.
 *************************************************************************/
#include "Falcor.h"
#include "Core/Plugin.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    // Intentionally empty — PathTraceCore deploys shared slang utilities only.
}
