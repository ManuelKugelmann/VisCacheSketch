/***************************************************************************
 # Common.cpp — no-op plugin shell for shared slang utilities.
 #
 # This plugin registers no render-pass class. Its sole purpose is to
 # produce a DLL that builds + deploys the shared slang files under
 # `runtime/shaders/RenderPasses/Common/`, from where other plugins import
 # them as `RenderPasses.Common.PathTraceCore`.
 *************************************************************************/
#include "Falcor.h"
#include "Core/Plugin.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    // Intentionally empty — Common deploys shared slang utilities only.
}
