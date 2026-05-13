/***************************************************************************
 # CacheCommon.cpp — no-op plugin shell for generic cache-primitive slang.
 #
 # Plugin name follows the *Common suffix family (PathTraceCommon,
 # ReSTIRCommon, future BDPTCommon). Hosts the cache-mechanics primitives
 # that are addressing/visibility/lineage agnostic: PCG hash family,
 # direction encoding, normal binning, salt constants.
 #
 # These were previously inside VisCache's USE_VISCACHE-guarded section;
 # ReSTIRPTPass had to maintain its own local pcg3d copy as a workaround.
 # Lifting them here drops the guard contract and gives every consumer a
 # single canonical home.
 #
 # Registers no render-pass class — purely deploys the shared slang module
 # under `runtime/shaders/RenderPasses/CacheCommon/`, importable as
 # `RenderPasses.CacheCommon.CacheHash`.
 #
 # When the full VisCache 3-way split lands (per the project memory):
 #   ReusableCache role  = CacheCommon (this) + cache-table mechanics
 #     (vhfTable buffer, vhfFindSlot, vhfInsert, vhfOverflowDecay, decay
 #      compute pass — currently still in VisCache)
 #   ReSTIR Utils role   = ReSTIRCommon (already populated)
 #   Visibility Cache role = VisCache (slimmed; algorithm: vhfGate,
 #                                     vhfCommit, CV+RRR, Bernoulli)
 *************************************************************************/
#include "Falcor.h"
#include "Core/Plugin.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    // Intentionally empty — CacheCommon deploys shared slang utilities only.
}
