/***************************************************************************
 # PathTraceCommon.cpp — no-op plugin shell for truly-common slang utilities.
 #
 # Plugin name suffix `Common` matches the lineage-shared family
 # (ReSTIRCommon, future ReSTIRPTCommon, future BDPTCommon). Sits one
 # layer below: PathTraceCommon hosts cross-lineage primitives that
 # every NEE consumer imports unconditionally, while the *Common
 # siblings host lineage-specific extensions.
 #
 # Registers no render-pass class. Exists purely to build + deploy
 # `PathTraceCore.slang` under `runtime/shaders/RenderPasses/PathTraceCommon/`,
 # importable as `RenderPasses.PathTraceCommon.PathTraceCore`.
 #
 # The slang file keeps its content-descriptive name (`PathTraceCore.slang`);
 # the plugin's job is deployment + namespacing, not naming the content.
 *************************************************************************/
#include "Falcor.h"
#include "Core/Plugin.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    // Intentionally empty — PathTraceCommon deploys shared slang utilities only.
}
