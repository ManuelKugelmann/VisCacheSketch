# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch — Visibility Prediction-with-Correction for real-time path tracing. Flat multilevel spatial hash cache with lock-free atomic updates, Bernoulli variance-driven adaptive sampling. Built as Falcor 8.0 render passes.

Paper: `viscachepaper/sections/*.md` → [GitHub Pages](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html). 2006 ancestor: `docs/references/Kugelmann2006_ThesisMK.pdf`.

## Directory Layout

- `Falcor/` — git subtree (not submodule); local fixes in `Falcor/LOCAL_FIXES.md`
- `Source/RenderPasses/VisCache/` — VisCache pass; see [`INTEGRATION.md`](Source/RenderPasses/VisCache/INTEGRATION.md) for ablation switches
- `Source/RenderPasses/ReSTIRPTPass/` — ReSTIR PT pass (DQLin, Falcor 8 port)
- `scripts/` — .py graph scripts, smoke tests, validation; `.scripts/` — shell wrappers
- `scenes/` — .pyscene configs (camera, lights, env map); see [`docs/PYSCENE_API.md`](docs/PYSCENE_API.md)
- `runtime/` — flat build output (`shaders/RenderPasses/`, `data/ReSTIRPTPass/`, `scripts/VisCache/`, `media/`)
- `viscachepaper/sections/*.md` — WIP paper content

## Build System

- **Always build via `build.bat`** — never invoke CMake/MSBuild directly
  - `build.bat --skip-setup` — incremental (skips packman/submodules)
  - `build.bat --clean` — full reconfigure (removes CMake cache)
- **Flat output to `runtime/`** — no `Debug/`/`Release/` subdirs; Mogwai CWD must be `runtime/`
- **Shader source of truth is `Source/`** — never edit under `runtime/shaders/`
- **Plugins via `FALCOR_PLUGIN_DIRS`** — `Source/RenderPasses/` builds from source, no copy into Falcor tree
- Packman fetches binary deps (CUDA, D3D12 Agility SDK, nvtt, slang, falcor_media/Arcade+TestScenes)
- CMake presets: `linux-gcc-ci`, `windows-vs2022-ci`, `windows-ninja-msvc-ci`; Windows requires SDK 10.0.19041.0 (`windows-2022` runner, NOT `windows-latest`)
- CMake macros: `target_copy_shaders`, `target_copy_data`, `target_copy_scripts`
- Default to **Debug builds** for ladder tests; Release only for timing benchmarks
- CI: `build.yml` (binaries+release), `validate.yml` (algorithm), `paper.yml` (GitHub Pages), `quickstart.yml`; runs `ubuntu-22.04` + `windows-2022`

## Scripting

- **Prefer `.bat` over `.ps1`** — PowerShell execution policies block `.ps1`
- **Run `.bat` directly from bash** — Git Bash invokes cmd.exe; do NOT wrap with `cmd.exe /c "..."` (output swallowed)
- `.bat` ROOT resolution: `for %%I in ("%~dp0..") do set "ROOT=%%~fI"` (clean absolute path, no `..`)
- Two `.gitmodules` (root + `Falcor/`) — use `sync-submodules.sh` to sync
- `.gitattributes`: LF everywhere, CRLF for `.bat`; Edit/Write tools strip `\r` — fine, repo is LF-normalized

## Scenes

- **Default: CornellBox** — procedural, no download; use for smoke tests and ladder tests
- **Arcade** — bundled with build, multi-light varied geometry; good for quick tests
- VeachAjar: `Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/` → `runtime/data/ReSTIRPTPass/VeachAjar/`
- Bistro/Sponza — separate download (~3.2 GB / ~70 MB) via `download_scenes.bat/sh`; Bistro needs scene type conformances in `setScene()` (ReSTIRPTPass.cpp)

## Quickstart / Launch Scripts

- `--renderer minimal|pathtracer|rtxdi|restirpt` (default: `restirpt`), `--variant vanilla|viscache`, `--scene`, `-i` (interactive)
- Graph scripts: `{Minimal,Path,RTXDI,ReSTIRPT}Tracer_Graph.py`; VisCache variants are thin wrappers calling vanilla with `viscache=True`
- VisCache is always a **variant**, never a renderer — there is no `renderer=viscache`

## `.scripts/` Wrapper Scripts

- **`.scripts/mogwai-headless.sh [--source|--synced] <pattern> [scene] [frames]`** — headless test, glob patterns OK
- **`.scripts/mogwai-headed.sh [--source|--synced] <pattern> [scene]`** — headed (GPU window) test
- **`.scripts/sync_to_runtime.sh [--synced]`** — hot-sync shaders+data; `--synced` also copies scenes+scripts (CI)
- **`.scripts/smoke.sh`** — 1-frame smoke test

**Mode resolution** (first match wins): `--source`/`--synced` flag → `VISCACHE_MODE` env → `.scripts/.mode` file (gitignored, default: `source`) → auto (`source` if `scripts/` exists, else `synced`). Source mode serves scripts/scenes from source tree; synced uses `runtime/` copies.

## Build + Test Workflow

1. **Build:** `build.bat --skip-setup` or `--clean` — calls `sync_to_runtime.sh` automatically; locked DLLs silently skip (yellow warning)
2. **Shader-only:** `.scripts/sync_to_runtime.sh` — no rebuild for `.slang`/`.py` changes
3. **Smoke test:** `.scripts/smoke.sh` (1 frame, MinimalPathTracer + VeachAjar)
4. **Ladder tests:** `.scripts/mogwai-headless.sh 'VisCache_Ladder00.py' [scene]`
   - Default scene: CornellBox. `SCENE_FILE` env or 2nd arg to override; `RES=1024` (default 512)
   - Captures to `runtime/captures/ladder/00/<SceneName>/`
5. **Full matrix:** `.scripts/mogwai-headless.sh '*_Graph.py'`

**Mogwai:** `run_graph_headless.py` calls `m.loadScene()` — do NOT use `--scene` flag (loads too late). Exit 0 = pass; check `Mogwai.exe.*.log` in `runtime/` on failure.

## Ladder Test System

Scripts in `scripts/VisCache_Ladder*.py`; shared infra in `VisCache_LadderCommon.py`.

- **Step 00** (`VisCache_Ladder00.py`): Vanilla baselines (no VisCache). Renders x1 SPP (error reference) + x32768 SPP (ground truth for noise measurement)
- **Step 01** (`VisCache_Ladder01.py`): First tests — all 10 addressing variants at default cell sizes (QUANT_SMALL). Runs VARIANTS_ALL across 4 CornellBox scene variants
- **Step 02** (`VisCache_Ladder02.py`): Quantization refinement — per-variant tuned bin sizes, x1 vs x32 SPP comparison
- **Variants** — naming: `A__B` separates endpoints, `_` separates dims, `1` = collapsed:
  - `pos_norm1__*` (5 variants, normal collapsed): pos1, dir1_dist1, pos, dir_dist1, dir_dist
  - `pos_norm__*` (5 variants, normal active ~60°/bin): pos1, dir1_dist1, pos, dir_dist1, dir_dist
  - Generated by `_make_variants(normal_active, quant)` from quantization presets
- **Quantization presets** (`QUANT_SMALL/MID/LARGE`): named bin-size bundles for cellB, angular, dist, normal
- **Error/noise baselines**: HDR pre-tonemapper EXR (AccumulatePass.output), OkLab perceptual distance with 2x L weight. Error = |viscache - vanilla_xN| (matching SPP). Noise = |viscache - vanilla_x32768| (ground truth)
- **Separate VisCache RNG**: `vcCreateSG(pixel)` — independent sample stream keeps vanilla/VisCache deterministically comparable
- **Diagnostic grid** (9 cols, 2 rows per variant):
  - Row 1 accum: render, raysTraced, error, maturity, mean, variance, coldmiss, posAHash, noise
  - Row 2 frame: level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, posBHash, probeSteps
- **Plates**: 4×3 diagnostic overview per variant with labels, exported to `docs/devlog/plates/`
- **Postprocess:** `viscache_exr.py` → viridis PNGs (Python/OpenEXR, no ffmpeg)
- **Extending:** add `VisCache_Ladder<NN>.py` steps; shared utilities in `VisCache_LadderCommon.py`; ladder scripts set `_HEADLESS_SCRIPT_DONE = True` instead of `exit()`

## Python

- **Always use `runtime/pythondist/python.exe`** — never system Python; `runtime/pythondist/python.exe -m pip install <pkg>`
- Never work in `Falcor/build/...` — only edit `Source/`, work in `runtime/`

## `.agents/` — Inter-Agent Communication

Gitignored folder for agent coordination. Two files:

**`.agents/shout`** — compact broadcast state, auto-injected every session (`SessionStart` always; `UserPromptSubmit` if changed). The hook injects `(session: <short-id>)` in the header — that's your key for `note` and `chat`. Keep it short.
```
mode: source  set-by:a1b2c3d4|date   # global; source|synced — keep in sync with .scripts/.mode
exp[a1b2c3d4]: -                     # active experiment, or "-"
worktree[a1b2c3d4]: -                # active worktree branch, or "-"
note[a1b2c3d4]: <freeform>           # your session's note — anything goes
note[e5f6a7b8]: <freeform>           # another session (read-only)
```
`mode` is global — one value, attributed with `set-by:sid|date`. All other fields are per-session, keyed by short ID. Write only to your own keys. Your short ID is the `self:` line injected at the top of the context.

**`.agents/handoff`** — append-only log for longer-form handoffs, findings, decisions. Not auto-injected — read when picking up a task.
```
---
by: <agent> | <date>
topic: <what>
<findings, decisions, next steps>
```

**Worktrees:** Use for risky/experimental work (refactors, experiments that might break main). `Agent` tool `isolation: "worktree"` creates a temp worktree automatically for subagents. Manual: `EnterWorktree`/`ExitWorktree` tools. Record active branch in `worktree:` field of `.agents/shout`.

## Workflow

- **No backwards compatibility** — move forward, no back-compat aliases or shims
- **No duplicated code** — extract shared logic into helpers; never copy-paste between scripts
- **Small incremental edits** — step by step for large changes; not massive Write calls
- **Fix all errors encountered**, even pre-existing ones
- **Never chain `cd &&` before commands** — wrap cd-requiring calls in `.scripts/` reusable scripts
- **No Co-Authored-By in commits** — no AI attribution lines
- **Color in CLI output** — highlight calls to action and salient findings
