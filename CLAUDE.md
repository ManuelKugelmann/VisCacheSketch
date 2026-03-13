# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch — Visibility Prediction-with-Correction for real-time path tracing. Flat multilevel spatial hash cache with lock-free atomic updates, Bernoulli variance-driven adaptive sampling. Built as Falcor 8.0 render passes.

Paper draft: `viscachepaper/sections/*.md` (combined at [GitHub Pages](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html)).
2006 ancestor: `docs/references/Kugelmann2006_ThesisMK.pdf` ("thesismk").

## Scripting

- **Prefer `.bat` over `.ps1`** for Windows scripts. PowerShell execution policies block `.ps1` by default. `.bat` works everywhere (cmd, PowerShell, CI).
- Install one-liner: `cmd /c "curl -sL <url>/scripts/install.bat?%RANDOM% -o %TEMP%\vc-install.bat && %TEMP%\vc-install.bat"`

## Falcor Subtree Policy

- Falcor is in `Falcor/` (git subtree, not submodule)
- **Keep Falcor files as close to the NVIDIA original as possible.** All VisCache-specific setup belongs in root scripts (`setup.sh`, `setup.bat`), not in Falcor's own files.
- Only acceptable Falcor modifications: upstream bug fixes or changes for ManuelKugelmann/Falcor fork
- Two `.gitmodules` files exist (root and `Falcor/.gitmodules`) — use `sync-submodules.sh` to keep in sync

## Build System

- Falcor submodules: shallow-cloned (subtree squash strips `.gitmodules`)
- NVIDIA packman fetches binary deps (CUDA, D3D12 Agility SDK, nvtt, slang)
- Linux: `libnvtt.so.30106` → `libnvtt.so` copy (see `Falcor/setup.sh`)
- CMake presets: `linux-gcc-ci`, `windows-vs2022-ci`, `windows-ninja-msvc-ci`
- Windows: SDK 10.0.19041.0 required (`windows-2022` runner, NOT `windows-latest`)

## Paper Workflow

- `viscachepaper/sections/*.md` — WIP paper content (edit directly)
- `viscachepaper/paper-sketch.md` — index/TOC only
- CI (`paper.yml`) combines sections into `paper-combined.md` → GitHub Pages
- PDF generation moving to LaTeX

## CI

- `.github/workflows/paper.yml` — Paper combine + GitHub Pages deploy
- `.github/workflows/validate.yml` — Algorithm validation tests
- `.github/workflows/build.yml` — Binary builds + release
- `.github/workflows/quickstart.yml` — Quickstart idempotency + CPU tests
- Runs on: `ubuntu-22.04` (Linux/GCC), `windows-2022` (VS2022 + Ninja/MSVC)

## Render Passes

- `Source/RenderPasses/VisCache/` — Visibility Cache pass
- `Source/RenderPasses/ReSTIRPTPass/` — ReSTIR PT pass (DQLin [Lin et al. SIGGRAPH 2022] ported to Falcor 8)
- Copied into Falcor source tree during setup/CI

## Line Endings

- `.gitattributes`: LF everywhere, CRLF for `.bat` files
- Edit/Write tools strip `\r` — fine since repo is LF-normalized

## Workflow

- Work step by step for large edits — small incremental Edit calls, not massive Write
- **Fix all errors encountered**, even pre-existing ones — do not discard or skip them because they were not introduced by the current task
