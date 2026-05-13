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
4. **Ladder runs (preferred):** `runtime/pythondist/python.exe scripts/run_ladder.py [-s STEPS] [-c SCENES]` — Python wrapper, native paths, per-scene Mogwai isolation. Each scene gets a fresh process to avoid Slang's internal-compiler fatigue (~60 shader permutations / process). Captures & CSV are upsert-keyed → safe to subset, cancel, rerun additively.
   - `-s "06"` / `-s "03 05 06 07"` / `-s 06,12` — bare numbers or full script names
   - `-c CornellBox_1AreaLight` / `-c "Arcade,Bistro"` — bare names or `.pyscene` (`.pyscene` auto-appended)
   - Defaults: all `VisCache_Ladder??.py` × `ALL_SCENES` from `VisCache_LadderCommon.py` (extend that list to add scenes)
   - Captures to `runtime/captures/ladder/<NN>/<SceneName>/`
5. **Single-script tests:** `.scripts/mogwai-headless.sh '<pattern>' [scene]` — for non-ladder graphs (e.g. `'*_Graph.py'`). For ladder steps prefer `run_ladder.py`.
6. **Same-process batch (advanced):** `LADDER_STEPS=... LADDER_SCENES=... mogwai-headless.sh RunLadderBatch.py` — runs everything in one Mogwai. Faster startup but risks Slang fatigue past ~60 permutations. Only for small sweeps.

**Mogwai:** `RunGraphHeadless.py` calls `m.loadScene()` — do NOT use `--scene` flag (loads too late). Exit 0 = pass; check `Mogwai.exe.*.log` in `runtime/` on failure.

## Ladder Test System

Scripts in `scripts/VisCache_Ladder*.py`; shared infra in `VisCache_LadderCommon.py`.

- **Step 00** (`VisCache_Ladder00.py`): Vanilla baselines (no VisCache). Renders x1 SPP (error reference) + x4096 SPP (ground truth for noise measurement)
- **Step 01** (`VisCache_Ladder01.py`): Cold-start tiling artifact demo. Single frame, coarse cells, mitigations (footprint scale, warmup write-only) ablated off
- **Step 02** (`VisCache_Ladder02.py`): `PRESET_MINIMAL` + `QUANT_SMALL`, always-trace. Isolates cache addressing accuracy
- **Step 03** (`VisCache_Ladder03.py`): Per-axis quant sweep (45 variants): qA×qB / qA×qD / qA×qD×qd via `build_per_axis_quant_variants`. Picks per B-variant top-3
- **Step 04** (`VisCache_Ladder04.py`): SPP convergence (x1/x4/x16) on step-03 top-3 per B-variant
- **Step 05** (`VisCache_Ladder05.py`): Threshold sweep (ct1/ct2/ct4) at step-04 winner + `FOOTPRINT_ON`
- **Step 06** (`VisCache_Ladder06.py`): varThreshold sweep (vt010/vt020/vt040) at step-05 winner — RR variance-gate
- **Step 09** (`VisCache_Ladder09.py`): Jitter sweep (single level) — jitterFilter / jitterCell
- **Step 10** (`VisCache_Ladder10.py`): Quant × threshold (multi-level) on pos__pos
- **Step 11** (`VisCache_Ladder11.py`): Level sweep (numLevels × quant-shift) at pinned winner
- **Step 14** (`VisCache_Ladder14.py`): Combined sweep: 2 quant × 2 threshold × 3 footprint (multi-level)
- Steps **07/08 retired**; their content merged into the renumbered ladder above
- **Presets**: `PRESET_MINIMAL` (others added as ladder steps demand them)
- **Building blocks**: `LEVELS_*`, `THRESH_*` (LOW/MID/HIGH), `RR_*` (OFF/FIXED/ADAPTIVE), `FEATURES_*`, `QUANT_*` (SMALL/MID), `SUBFRAME_2x2`, `FOOTPRINT_ON`
- **Variants** — naming: `A__B` separates endpoints, `_` separates dims, `1` = collapsed:
  - `pos_norm1__*` (normal collapsed), `pos_norm__*` (normal active ~60°/bin)
  - Per-axis tags: `qA<NN>` = posA×100, `qB<NN>` = posB×100, `qD<NN>` = dirB (°), `qd<NN>` = distB×100; thresholds `th<N>`, varThresh `vt<NN0>`, jitter `jf<N>` / `jc<N>`, footprint `fp<N>` or `fpOn`/`fpOff`
- **picks.json** (per step): machine-readable winner record in `captures/ladder/<NN>/`. Fields: `step`, `inherited_from`, `inherited`, `carried`, `rule`, `notes`. Written by `finalize_step` via `write_picks_meta`
- **Winner picker** (`pick_top_variants_per_bvariant`): rule is "err non-positive OR ≤ median+25%, blob non-positive OR ≤ median+50% (weighted across scenes, 32PointLights × 3); noise informational only; rank by rays_traced_pct asc". Median-gated rays-savings — never picks a variant that introduces visible artifacts. Blob tolerance is wider than err because the worst-blob metric is naturally noisier (max over Gaussian-smoothed region across scenes); a strict 25% cut was excluding aggressive-quant variants with modestly above-median blob
- **Cross-step progress plot** (`plot_ladder_progress`): `captures/ladder/ladder_progress.png` — 3 panels (rays / error+blob / noise), per-scene thin lines + bold weighted-"All" (SCENE_WEIGHTS = 32PL×3), min-to-max whiskers per scene per step. Auto-refreshed by every `finalize_step`
- **`finalize_step`** signature: `finalize_step(step_name, prev_winner=None, carried_winners=None, inherited_winners=None, skip_overview=False, ref_step=None, ref_variant=None, ref_label=None)`. `carried_winners` overrides the auto-picker (manual override for visual/artifact calls). `ref_step`+`ref_variant` overlay loads rows from another step's CSV and renders them as red stars for direct cross-step comparison — see step 10 pointing at step 05's single-level winner
- **Plot markers**: red circle halo = carried-forward winner (fixed size, independent of SPP); thin red whisker end-tick = that winner's max-blob tip on the error-Δ panel; red star = prior-step reference (resolved via `ref_step`/`ref_variant`, rendered at each scene + weighted "All" column, sized by SPP)
- **Adaptive legend** (`_add_adaptive_legend`): scales columns/font by entry count — 1 col ≤40, 2 cols ≤60, 3 cols ≤80, 4 cols ≤100, hidden >100 (hue/sat/alpha/shape already encode the axes). Applied to both single-panel and combined plots
- **Variant sort**: when variant name contains `L<N>` token (step 10+ multi-level), level count is primary sort key so L4→L6→L8→L16 reads left-to-right within each scene column. Otherwise falls back to B-core rank × tag rank
- **Scenes**: `ALL_SCENES` (4 Cornell variants) = default for steps 00–06. `MULTI_LEVEL_SCENES` (32PointLights + BistroInterior/Exterior + Sponza) = default for steps 11+. Resolved via `get_scenes(default=MULTI_LEVEL_SCENES)` — accepts `SCENES`/`SCENE_FILE` env-var overrides. Single-area/point-light Cornells contribute little signal once the cascade is active
- **`plot_overviews_per_bvariant(step, variant_filter=...)`**: optional `callable(variant_name)->bool` applied within each B-variant grouping, to show a subset of a dense sweep without rerunning. Filter must pass-through non-targeted B-variants (e.g. step 03 dir_dist trimmed to 3×2×2 = 12 for legend fit, with `pos` / `dir_dist1` returning True unconditionally)
- **quantSceneScale** option (VisCache.h/cpp): opt-in flag — treat posA/posB/distB as fractions of Cornell reference (avgAxis=2 units). Cells scale with scene size across Bistro/Sponza. Overridden by `autoTuneCells`
- **Error/noise baselines**: HDR pre-tonemapper EXR (AccumulatePass.output), OkLab perceptual distance with 2x L weight. Error = |viscache - vanilla_xN| (matching SPP). Noise = |viscache - vanilla_x32768| (ground truth)
- **Separate VisCache RNG**: `vcCreateSG(pixel)` — independent sample stream keeps vanilla/VisCache deterministically comparable
- **Diagnostic grid** (9 cols, 2 rows per variant):
  - Row 1 accum: render, raysTraced, error, maturity, mean, variance, coldmiss, posAHash, noise
  - Row 2 frame: level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, posBHash, probeSteps
- **Plates**: 4×3 diagnostic overview per variant with labels, exported to `docs/devlog/plates/`
- **Postprocess:** `viscache_exr.py` → viridis PNGs (Python/OpenEXR, no ffmpeg)
- **Extending:** add `VisCache_Ladder<NN>.py` steps; shared utilities in `VisCache_LadderCommon.py`; ladder scripts set `_HEADLESS_SCRIPT_DONE = True` instead of `exit()`
- **Devlog style** (`docs/devlog/DEVLOG.md`): one entry per ladder step, **ladder-log not dev-history**. Per entry: (1) current config (preset/quant/sweep axes in 1–2 lines), (2) key insights the ladder data reveals, (3) open points / possible improvements. Always reflects the *newest* state + successful validations — rewrite in place when things change, do **not** append debug chronicles, commit descriptions, or fix narratives (those belong in the git log). Keep the current-step-result plate image at the bottom.

## Python

- **Always use `runtime/pythondist/python.exe`** — never system Python; `runtime/pythondist/python.exe -m pip install <pkg>`
- Never work in `Falcor/build/...` — only edit `Source/`, work in `runtime/`

## Recovery artefacts (local-only, not committed)

`scripts/VisCache_LadderCommon.py` was truncated to 0 bytes during a disk-full write on 2026-04-21 23:05. It has been reconstructed from the session `.pyc` backup. These files are **excluded via `.git/info/exclude`** and must stay local:

- `VisCache_LadderCommon_session.pyc_backup` — intact bytecode at session state (md5 6e28191a40d9b3f851ffb9580f5edbdd)
- `VisCache_LadderCommon_githead.py.bak` — git-HEAD pre-session fallback
- `_recovery_diff.py` — bytecode fingerprint validator (ref .pyc vs current compiled source)
- `_recovery_session_changes.md` / `_recovery_session_reads.md` / `_recovery_this_session_notes.md` — per-function reconstruction notes and post-.pyc edit log (A.1–A.8)
- `_plot_metric_replacement.py` / `_add_nested_docstrings.py` — ad-hoc patchers used during reconstruction

Current diff state: 122 match / 11 diff (4 expected from post-.pyc edits, 7 implementation drift — functionally correct but not byte-identical). Keep the artefacts as an audit trail until the ladder stack has proven stable across several runs.

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

Update `note[sid]:` when your status changes: renames, mode switches, active experiment, blockers, what you just finished. One line only — it lands in every prompt. Update `mode:`/`worktree:` if you changed them.

**Always read `.agents/shout` before writing it.** Patch only your own keyed lines and `mode:` (if changed); preserve all other sessions' lines. Never overwrite the whole file cold.

**`.agents/handoff`** — append-only log for longer-form handoffs, findings, decisions. Not auto-injected — read when picking up a task. Use for: design decisions, non-obvious fixes, multi-step findings, anything needing more than one line.
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
- **Cbuffer cross-pass binding: every field must be enumerated.** Falcor 8's `setBuffer()` only handles SRV/UAV — `ConstantBuffer`-typed shader vars cannot be bound by passing a `ref<Buffer>`, so cross-pass cbuffer wiring (e.g. PathTracer reading `VisCacheParams` populated by VisCache pass) MUST enumerate every field: `var["VisCacheParams"]["gFooField"] = mVCParams.fooField;`. **Whenever you add a field to the C++ `GPUParams` struct + the slang `cbuffer VisCacheParams`, you MUST also add it to every per-field binding site** (`Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp` tracePass + `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp` PathRetrace/PathReuse). Forgetting any field leaves the shader global at its default (0) and produces "shader sees wrong value despite C++ writing the right one" bugs that are very hard to diagnose (the C++ memcpy buffer is correct; only the per-field bindings in PathTracer/ReSTIRPTPass matter for those passes).
- **Small incremental edits** — step by step for large changes; not massive Write calls
- **Fix all errors encountered**, even pre-existing ones
- **Never chain `cd &&` before commands** — do a solo `cd` in a separate Bash call, then run commands from there
- **No Co-Authored-By in commits** — no AI attribution lines
- **Color in CLI output** — highlight calls to action and salient findings
- **Use the FULL battery of available metrics when evaluating sweep results** — never report only `mean_err_pct` (OkLab) or only `art5_pct`. The variant-CSV schema includes RMSE, PSNR, relmse, MS-SSIM, FLIP, smape, mape, art_{3,5,11}, mean_noise — each measures a different failure mode. Single-metric analysis MISSES the trade-offs: the cache trades linear-space variance (RMSE/PSNR) for rays cost while preserving perceptual quality (OkLab/MS-SSIM); vt has anti-correlated optima between art5 (local spike penalty) and RMSE (global average). Tables and prose conclusions must report at minimum: err%, art5%, RMSE, PSNR, rays% — and call out when metrics disagree about the winner.
- **Don't hide or ignore errors — find the root cause.** When a build fails, a kernel TDRs, a test crashes, or a smoke test regresses, do not fall back to "stable state with placeholder" and call it progress. That hides the real problem and lets bugs accumulate. Solutions you can use: (1) read the relevant reference code (e.g. `Source/RenderPasses/ReSTIRPTPass/`, `Falcor/Source/RenderPasses/PathTracer/`, `Falcor/external/packman/rtxdi/`) to see how the working pattern looks; (2) launch an Explore subagent to map related code; (3) WebSearch for the specific error message or compiler-version interaction; (4) bisect to a minimal reproducer and post the diagnostic to `.agents/handoff` for cross-session continuity. **Reverting to placeholders or commenting out the failing code is allowed only as a temporary safety net while actively investigating** — every iteration must move the diagnosis forward, not just preserve the green tests.
- **Do NOT work around requirements.** When the user states a requirement (e.g. "N=1024 for RTXDI comparability") and the obvious implementation hits a difficulty (DXIL limit, perf cost, alignment issue), the correct response is to RE-ARCHITECT around the difficulty — change data layout, split buffers, switch access pattern — NOT to defer or substitute a "good enough" smaller value. "Deferred until..." is a euphemism for "skipped the requirement"; reject it. If the requirement seems infeasible, surface that explicitly to the user with a concrete cost/alternatives analysis rather than silently downgrading.
