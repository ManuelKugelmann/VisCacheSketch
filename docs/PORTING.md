# DQLin/ReSTIR_PT → Falcor 8.0 Port Guide

Estimated time: **1–2 days** (mechanical changes, no algorithmic changes).
The Slang shaders require only MLVHF-specific additions (see delta files).
The C++ host code requires Falcor API migration.

---

## 0. Before you start

Clone the upstream repo:
```
git clone --depth 1 https://github.com/DQLin/ReSTIR_PT.git upstream/
```

Work in a branch:
```
git checkout -b falcor8-port
```

---

## 1. C++ API migration (global search-replace)

| Old (Falcor 5.2) | New (Falcor 8.0) | Notes |
|---|---|---|
| `SharedPtr<X>` | `ref<X>` | All smart pointer types |
| `X::SharedPtr` | `ref<X>` | Typedef aliases |
| `X::create(...)` | `make_ref<X>(...)` or factory | Check per-class |
| `Program::Desc` | `ProgramDesc` | Top-level namespace |
| `Shader::DefineList` | `DefineList` | Moved namespace |
| `Scene::SharedPtr` | `ref<Scene>` | Standard |
| `Buffer::createStructured(device, elem, count, flags)` | `device->createStructuredBuffer(elem, count, flags, MemoryType::DeviceLocal)` | Signature changed |
| `Buffer::createTyped<T>(...)` | `device->createBuffer(size, flags, MemoryType::...)` | Now typed at access |
| `renderData.getDictionary()["key"]` | `renderData.getDictionary()["key"]` | Same, but `InternalDictionary` renamed in docs |
| `Gui::Window` | `Gui::Widgets` | UI widget renamed |
| `pRenderContext->flush()` | `pRenderContext->submit(false)` | Renamed |

---

## 2. RenderPass interface changes

### compile()
```cpp
// Old (5.2)
void compile(RenderContext* pCtx) override;

// New (8.0)
void compile(RenderContext* pCtx, const CompileData& compileData) override;
```

### reflect()
```cpp
// Old (5.2)
RenderPassReflection reflect() override;

// New (8.0)
RenderPassReflection reflect(const CompileData& compileData) override;
```

### Plugin registration
```cpp
// Old (5.2)
extern "C" __declspec(dllexport) void getPasses(Falcor::RenderPassLibrary& lib) {
    lib.registerClass("ReSTIRGIPass", "...", ReSTIRGIPass::create);
}

// New (8.0)
FALCOR_PLUGIN_CLASS(ReSTIRGIPass, "ReSTIRGIPass", "...");
extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry) {
    registry.registerClass<RenderPass, ReSTIRGIPass>();
}
```

---

## 3. CMakeLists.txt

Replace the entire CMakeLists.txt with the Falcor 8 plugin pattern:

```cmake
add_plugin(ReSTIRGIPass)
target_sources(ReSTIRGIPass PRIVATE
    ReSTIRGIPass.h
    ReSTIRGIPass.cpp
)
target_copy_shaders(ReSTIRGIPass
    # list all .slang files
)
target_link_libraries(ReSTIRGIPass PRIVATE Falcor)
```

Then add to `Source/RenderPasses/CMakeLists.txt`:
```cmake
add_subdirectory(ReSTIRGIPass)
```

---

## 4. Slang shader changes (minimal)

Falcor 8 uses Slang 2024.1.34. The upstream shaders use Slang as well;
most will compile without changes. Known issues:

- `import Scene;` path may need adjustment to match Falcor 8 layout.
- `ShadingData` struct fields may have minor name changes — compare with
  `Source/Scene/Shading.slang` in Falcor 8.
- `TraceRayInline()` API is unchanged (DXR 1.1).

---

## 5. MLVHF integration (after port compiles)

Once the base port compiles and produces correct output on Bistro:

1. Add `#import "../VisHashFilter/VisHashFilter"` at the top of `SpatialReuse.cs.slang`
2. Replace the visibility ray block with `evalRevalidationCV()` — see
   `Source/RenderPasses/ReSTIRGIPass/SpatialReuse_MLVHF_delta.slang`
3. In `ReSTIRGIPass::execute()`, call `retrieveVHFBuffers(renderData)` before
   dispatching the spatial reuse compute shader — see delta file.
4. Verify ground truth: disable MLVHF (`useMLVHFRevalidation = false`) and
   confirm the ported pass matches DQLin paper figures on Bistro.

---

## 6. Verification checklist

- [ ] Unmodified port matches DQLin reference images on Bistro (FLIP < 0.01)
- [ ] ReSTIR GI produces k=5.0 traces/pixel with revalidation, MLVHF disabled
- [ ] After MLVHF enable: traces/pixel drops to ~0.5–1.0 at steady state
- [ ] MSE vs. reference within 5% of full-retrace baseline at equal time
- [ ] No NaN or Inf in output (check via `pCtx->clearDebugCounters()`)
