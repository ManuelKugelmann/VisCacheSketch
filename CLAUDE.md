# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch — Visibility Prediction-with-Correction for real-time path tracing. Flat multilevel spatial hash cache with lock-free atomic updates, Bernoulli variance-driven adaptive sampling. Built as Falcor 8.0 render passes.

Paper: `viscachepaper/sections/*.md` → [GitHub Pages](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html). 2006 ancestor: `docs/references/Kugelmann2006_ThesisMK.pdf`.

## Directory Layout & Paths

- `Falcor/` — git subtree (not submodule), keep close to NVIDIA original; local bug fixes listed in `Falcor/LOCAL_FIXES.md`
- `Source/RenderPasses/VisCache/` — Visibility Cache pass; see [`INTEGRATION.md`](Source/RenderPasses/VisCache/INTEGRATION.md) for per-renderer integration details and ablation switches
- `Source/RenderPasses/ReSTIRPTPass/` — ReSTIR PT pass (DQLin, Falcor 8 port)
- `scripts/` — .py graph scripts, smoke tests, validation scripts
- `.scripts/` — shell wrappers for common operations (build, test, deploy)
- `scenes/` — .pyscene scene configs (camera, lights, env map); see [`docs/PYSCENE_API.md`](docs/PYSCENE_API.md) for Falcor 8 API reference
- `runtime/` — build output directory (CMake builds directly here via `FALCOR_RUNTIME_OUTPUT_DIRECTORY`)
  - `runtime/shaders/RenderPasses/` — deployed .slang shaders
  - `runtime/data/ReSTIRPTPass/` — data files (e.g. 16RooksPattern256.txt)
  - `runtime/scripts/VisCache/` — graph configs and smoke tests
  - `runtime/media/` — all scene assets (Arcade + TestScenes bundled from CI; Bistro, Sponza downloaded)
- `viscachepaper/sections/*.md` — WIP paper content

## Scripting

- **Prefer `.bat` over `.ps1`** — PowerShell execution policies block `.ps1`
- **Run `.bat` files directly from bash** — Git Bash executes them via cmd.exe automatically; do NOT wrap with `cmd.exe /c "..." 2>&1` as output gets swallowed
- All .bat scripts resolve ROOT with `for %%I in ("%~dp0..") do set "ROOT=%%~fI"` (clean absolute path, no `..`)
- Two `.gitmodules` (root + `Falcor/`) — use `sync-submodules.sh` to sync

## Build System

- **External plugin builds via `FALCOR_PLUGIN_DIRS`** — plugins in `Source/RenderPasses/` build directly from source, no copy into Falcor tree needed. `build.bat` passes `-DFALCOR_PLUGIN_DIRS=...` to cmake.
- **Build output goes directly to `runtime/`** — flat output, no `Debug/`/`Release/` subdirectory. Mogwai working directory must be `runtime/`, never `runtime/Release/`. All paths (scripts, captures, shaders) are relative to `runtime/`
- Packman fetches binary deps (CUDA, D3D12 Agility SDK, nvtt, slang); also `falcor_media` (Arcade, TestScenes)
- CMake presets: `linux-gcc-ci`, `windows-vs2022-ci`, `windows-ninja-msvc-ci`
- Windows: SDK 10.0.19041.0 required (`windows-2022` runner, NOT `windows-latest`)
- CMake macros for plugin assets:
  - `target_copy_shaders(target subdir)` — deploys .slang files
  - `target_copy_data(target subdir)` — deploys `Data/` subdirectory
  - `target_copy_scripts(target subdir)` — deploys `Scripts/` subdirectory
- **Shader source of truth is `Source/`**, not `runtime/shaders/` — only edit under `Source/RenderPasses/`
- **Always build via `build.bat`** — never invoke CMake/MSBuild directly. If functionality or granularity is missing, add it to `build.bat`
- **Quick build:** `build.bat --skip-setup` (skips packman/submodules, just configure+build)
- **Clean rebuild:** `build.bat --clean` (removes CMake cache, full reconfigure)
- **Default to Debug builds** for initial ladder tests — Release is only needed for timing benchmarks
- **Flat output:** `build.bat` passes `-DFALCOR_FLAT_OUTPUT=ON` so all configs output directly to `runtime/` (no `Release/`/`Debug/` subdirectory)

## CI

- `paper.yml` — paper combine + GitHub Pages
- `validate.yml` — algorithm validation tests
- `build.yml` — binary builds + release (bundles Arcade + TestScenes in archive)
- `quickstart.yml` — quickstart idempotency + CPU tests
- Runs on: `ubuntu-22.04`, `windows-2022`

## Line Endings

- `.gitattributes`: LF everywhere, CRLF for `.bat` files
- Edit/Write tools strip `\r` — fine since repo is LF-normalized

## Scenes

- **Default test scene: CornellBox** — procedural (no download), use for smoke tests, ladder tests, and general testing unless stated otherwise
- **Use Arcade for quick tests** — bundled with the build, multi-light scene with varied geometry
- VeachAjar (DQLin ReSTIR PT reference scene) — small, no download needed after data deploy
- VeachAjar lives in source tree: `Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/`, deployed to `runtime/data/ReSTIRPTPass/VeachAjar/`
- Bistro/Sponza require separate downloads (~3.2 GB / ~70 MB) via `download_scenes.bat/sh`
- Bistro uses material types not statically imported by ReSTIRPTPass shaders — requires scene type conformances (see `setScene()` in ReSTIRPTPass.cpp)

## Quickstart / Launch Scripts

- Scripts support `--renderer`, `--variant`, `--scene`, and `--interactive` flags
- Renderers: `minimal` (MinimalPathTracer), `pathtracer` (Falcor PathTracer), `rtxdi` (ReSTIR DI), `restirpt` (ReSTIR PT) — default: `restirpt`
- Variant: `--variant vanilla` (no VisCache) or `--variant viscache` (with VisCache) — applies to all renderers
- Interactive mode (`-i`): numbered menus for renderer, variant, and scene selection
- Graph scripts (vanilla): `MinimalPathTracer_Graph.py`, `PathTracer_Graph.py`, `RTXDI_Graph.py`, `ReSTIRPT_Graph.py`
- Graph scripts (VisCache): `MinimalPathTracer_VisCache_Graph.py`, `PathTracer_VisCache_Graph.py`, `RTXDI_VisCache_Graph.py`, `ReSTIRPT_VisCache_Graph.py` — thin wrappers that call vanilla with `viscache=True`
- Each vanilla graph script accepts `viscache=True` to add the VisCache pass; no code duplication between vanilla and VisCache variants
- There is no `renderer=viscache` — VisCache is always a variant, not a renderer

## `.scripts/` Wrapper Scripts

Reusable wrappers for common operations (avoids `cd release` boilerplate):

- **`.scripts/mogwai-headless.sh <pattern> [scene] [frames]`** — headless test, supports glob patterns (e.g. `*_Graph.py`)
- **`.scripts/mogwai-headed.sh <pattern> [scene]`** — headed (GPU window) test
- **`.scripts/sync_to_runtime.sh`** — hot-sync shaders, scripts, data from source to `runtime/` without rebuilding; clears shader cache
- **`.scripts/smoke.sh`** — quick build validation (1 frame with scene)

## Build + Test Workflow

1. **Build:** `build.bat --skip-setup` (incremental) or `build.bat --clean` (full reconfigure)
   - Build calls `sync_to_runtime.sh` automatically after compilation
   - CMake outputs binaries directly to `runtime/` via `FALCOR_RUNTIME_OUTPUT_DIRECTORY`
   - If DLLs are locked (Mogwai still running), build may silently skip copy — sync warns with yellow text
2. **Shader-only iteration:** `.scripts/sync_to_runtime.sh` (no rebuild needed for .slang/.py changes)
3. **Quick smoke test:** `.scripts/smoke.sh` (1 frame, MinimalPathTracer + VeachAjar)
4. **Ladder tests:** `.scripts/mogwai-headless.sh 'VisCache_Ladder00.py' [scene]`
   - Default scene: CornellBox (procedural, no download). Override via 2nd arg or `SCENE_FILE` env var
   - Resolution: `RES=1024` env var (default 512)
   - Captures to `runtime/captures/ladder/00/<SceneName>/`
5. **Full test matrix:** `.scripts/mogwai-headless.sh '*_Graph.py'` (all renderer×variant combos)

## Testing with Mogwai

- **Scene loading:** `run_graph_headless.py` loads the scene via `m.loadScene()` inside the script (NOT via Mogwai's `--scene` flag, which loads too late)
- Graph scripts live in `runtime/scripts/VisCache/` (synced from `scripts/`)
- Exit code 0 = success; check Mogwai.exe.*.log in runtime/ for errors

## Ladder Test System

Systematic verification of VisCache addressing modes and cache behavior. Scripts in `scripts/VisCache_Ladder*.py`, shared infra in `VisCache_LadderCommon.py`.

- **Step 00** (`VisCache_Ladder00.py`): Single frame with 1 warmup frame. Tests hash table insert/lookup + diagnostic pipeline across all addressing variants
- **Step 01** (`VisCache_Ladder01.py`): Multi-frame accumulation. Tests cache convergence over time
- **Variants** (defined in `VisCache_LadderCommon.py`):
  - `pos_pos` — canonical pos×pos (cellA==cellB, hash-based canonicalization)
  - `posA_posB` — asymmetric pos×pos (cellB slightly different, no canonicalization)
  - `pos_pos1` — position-only (cellB collapsed to single bucket)
  - `pos_dir1_dist1` — dirdist path, both collapsed (equivalent to position-only)
  - `pos_dir_dist1` — dirdist with angular bins, distance collapsed
  - `pos_dir_dist` — dirdist with both angular + distance bins
- **Diagnostic output** (9-column viridis grid per variant, 2 rows):
  - Row 1 (accum): render, raysTraced, error, maturity, mean, variance, coldmiss, posAHash, noise
  - Row 2 (frame): level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, posBHash, probeSteps
- **Postprocess:** `viscache_exr.py` extracts EXR channels → viridis pseudocolor PNGs (Python, no ffmpeg)
- **Extending the ladder:** add new `VisCache_Ladder<NN>.py` steps. Extract reusable utilities into `VisCache_LadderCommon.py` to avoid duplication across steps

## Python

- **Always use Falcor's embedded Python** at `runtime/pythondist/python.exe` — never system Python
- Install packages via `runtime/pythondist/python.exe -m pip install <pkg>`
- Mogwai scripts run in this Python automatically; external scripts should use the same interpreter
- **Never work inside intermediary build folders** (`Falcor/build/...`) — only edit `Source/` and work in `runtime/`

## Workflow

- **No backwards compatibility** — move forward, don't maintain back-compat aliases or shims
- **No duplicated code** — extract shared logic into helper scripts; never copy-paste between .bat/.sh files
- Work step by step for large edits — small incremental Edit calls, not massive Write
- **Fix all errors encountered**, even pre-existing ones
- **Never prefix git/shell commands with `cd`** — wrap cd-requiring calls into reusable scripts in `.scripts/`; never chain `cd &&` before commands
- **No Co-Authored-By or similar tags in commit messages** — do not add AI attribution lines
- **Display calls to action and salient info with color in CLI output** — e.g. highlight "Should I fix that?" or important findings so they stand out
