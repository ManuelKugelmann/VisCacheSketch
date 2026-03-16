// slang-ci-stubs.slang — Minimal CI-only declarations for offline compilation.
//
// At runtime, Falcor's MaterialSystem::getTypeConformances() provides
// concrete IMaterial/IMaterialInstance conformances.  For offline CI we
// import StandardMaterial which provides these conformances.
//
// NOT shipped in the build — CI only.

#pragma once

// --- Material conformance (real Falcor code, not a stub) ---
import Rendering.Materials.StandardMaterial;
