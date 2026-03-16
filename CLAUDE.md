# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch — Visibility Prediction-with-Correction for real-time path tracing. Flat multilevel spatial hash cache with lock-free atomic updates, Bernoulli variance-driven adaptive sampling. Built as Falcor 8.0 render passes.

Paper: `viscachepaper/sections/*.md` → [GitHub Pages](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html). 2006 ancestor: `docs/references/Kugelmann2006_ThesisMK.pdf`.

## Directory Layout & Paths

- `Falcor/` — git subtree (not submodule), keep close to NVIDIA original; local bug fixes listed in `Falcor/LOCAL_FIXES.md`
- `Source/RenderPasses/VisCache/` — Visibility Cache pass
- `Source/RenderPasses/ReSTIRPTPass/` — ReSTIR PT pass (DQLin, Falcor 8 port)
- `scripts/` — .bat + .sh for quickstart, download, run, test
- `scenes/` — .pyscene scene configs (camera, lights, env map); see [`docs/PYSCENE_API.md`](docs/PYSCENE_API.md) for Falcor 8 API reference
- `release/` — extracted release bundle from GitHub Releases (replaces need for local build)
  - `release/shaders/RenderPasses/` — deployed .slang shaders (Falcor runtime looks here)
  - `release/data/ReSTIRPTPass/` — data files (e.g. 16RooksPattern256.txt)
  - `release/scripts/VisCache/` — graph configs and smoke tests
  - `release/media/` — all scene assets (Arcade + TestScenes bundled from CI; Bistro, Sponza downloaded)
- `viscachepaper/sections/*.md` — WIP paper content

## Scripting

- **Prefer `.bat` over `.ps1`** — PowerShell execution policies block `.ps1`
- All .bat scripts resolve ROOT with `for %%I in ("%~dp0..") do set "ROOT=%%~fI"` (clean absolute path, no `..`)
- Two `.gitmodules` (root + `Falcor/`) — use `sync-submodules.sh` to sync

## Build System

- Packman fetches binary deps (CUDA, D3D12 Agility SDK, nvtt, slang); also `falcor_media` (Arcade, TestScenes)
- CMake presets: `linux-gcc-ci`, `windows-vs2022-ci`, `windows-ninja-msvc-ci`
- Windows: SDK 10.0.19041.0 required (`windows-2022` runner, NOT `windows-latest`)
- `target_copy_shaders()` deploys .slang to `${FALCOR_OUTPUT_DIRECTORY}/shaders/RenderPasses/<pass>/`
- Render passes copied into Falcor source tree during setup/CI
- **Shader source of truth is `Source/`**, not `release/shaders/` — build/CI deploys shaders into `release/shaders/` automatically, so only edit under `Source/RenderPasses/`

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

- **Default test scene: VeachAjar** (DQLin ReSTIR PT reference scene) — small, no download needed after data deploy
- VeachAjar lives in source tree: `Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/`, deployed to `release/data/ReSTIRPTPass/VeachAjar/`
- Bistro/Sponza require separate downloads (~3.2 GB / ~70 MB) via `download_scenes.bat/sh`
- Bistro uses material types not statically imported by ReSTIRPTPass shaders — requires scene type conformances (see `setScene()` in ReSTIRPTPass.cpp)

## Quickstart / Launch Scripts

- Scripts support `--renderer`, `--variant`, `--scene`, and `--interactive` flags
- Renderers: `minimal` (MinimalPathTracer), `pathtracer` (Falcor PathTracer), `rtxdi` (ReSTIR DI), `restirpt` (ReSTIR PT), `viscache` (full VisCache pipeline)
- Variant: `--variant vanilla` (no VisCache) or `--variant viscache` (with VisCache) — applies to pathtracer, rtxdi, restirpt
- Interactive mode (`-i`): numbered menus for renderer, variant, and scene selection
- Graph scripts (vanilla): `MinimalPathTracer_Graph.py`, `PathTracer_Graph.py`, `RTXDI_Graph.py`, `ReSTIRPT_Graph.py`, `VisCache_Graph.py`
- Graph scripts (VisCache variants): `MinimalPathTracer_VisCache_Graph.py`, `PathTracer_VisCache_Graph.py`, `RTXDI_VisCache_Graph.py`
- `--variant viscache` maps each renderer to its specific VisCache graph (not the full pipeline); `restirpt --variant viscache` uses `VisCache_Graph.py` (full pipeline)

## Workflow

- Work step by step for large edits — small incremental Edit calls, not massive Write
- **Fix all errors encountered**, even pre-existing ones
