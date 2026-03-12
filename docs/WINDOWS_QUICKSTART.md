# Windows Quickstart

Get VisCacheSketch running on Windows in under 10 minutes.

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 (build 19041+) | Windows 11 |
| Visual Studio | 2022 (Desktop C++ workload) | Latest update |
| Windows SDK | 10.0.19041.0 | 10.0.19041.0 (exact) |
| CUDA | 12.x | 12.x |
| GPU | RTX 20xx (DXR 1.1) | RTX 30xx/40xx (SM 6.5, WaveMatch) |
| Python | 3.8+ | 3.10+ |
| Git | Any | Latest |

**VS2022 workloads** (via Visual Studio Installer):
- "Desktop development with C++"
- Individual component: "Windows 10 SDK (10.0.19041.0)"

## Option A: One-click quickstart (pre-built release)

**Single-line bootstrap (paste into cmd or PowerShell):**

```powershell
powershell -NoProfile -c "irm https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.ps1 | iex"
```

Or equivalently (if you prefer `git clone`):

```bat
git clone https://github.com/ManuelKugelmann/VisCacheSketch.git && cd VisCacheSketch && scripts\quickstart.bat
```

This will:
1. Download the latest pre-built release (Mogwai + plugins)
2. Download test scenes (Bistro ~3.2 GB, Sponza ~70 MB)
3. Run 43 CPU algorithm tests
4. Launch Mogwai with Bistro

**Quickstart options:**

```bat
scripts\quickstart.bat --scene Sponza      &REM launch with Sponza instead of Bistro
scripts\quickstart.bat --skip-scenes       &REM skip scene download (faster)
```

## Option B: Build from source

### 1. Clone

```bat
git clone https://github.com/ManuelKugelmann/VisCacheSketch.git
cd VisCacheSketch
```

### 2. Run setup

```bat
.\setup.bat
```

This calls Falcor's own setup (submodule init, NVIDIA packman deps, generates VS2022 `.sln`), then copies VisCache plugins into the Falcor tree, patches CMake, and runs CPU tests.

### 3. Build in Visual Studio

1. Open `Falcor\build\windows-vs2022\Falcor.sln`
2. Set configuration to **Release**, platform to **x64**
3. Build target: **Mogwai**

Or build from command line with CMake:

```bat
cmake --preset windows-vs2022-ci
cmake --build build --config Release --target Mogwai
```

### 4. Download test scenes

```bat
scripts\download_scenes.bat              &REM interactive (prompts per scene)
scripts\download_scenes.bat --yes        &REM download all scenes non-interactively
```

### 5. Run

```bat
Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene media\Bistro\Bistro_Interior.pyscene
```

Set `FALCOR_MEDIA_FOLDERS` to avoid full paths:

```bat
set FALCOR_MEDIA_FOLDERS=media
Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene Bistro_Interior.pyscene
```

## Running tests

CPU algorithm tests (no GPU required):

```bat
scripts\run-tests.bat              &REM all 43 tests (convergence + ReSTIR + ablation)
scripts\run-tests.bat quick        &REM convergence tests only (14 tests)
```

Smoke test (requires built Mogwai):

```bat
Mogwai.exe --headless --script scripts\VisCache\smoke_test.py
```

## Running experiments

```bat
REM Ablation captures (10 configs, 200 warmup + 16 capture frames each)
Mogwai.exe --headless --script scripts\VisCache\VisCache_Ablation.py --scene Bistro_Interior.pyscene

REM Baseline captures (14 DI/GI/PT configs)
Mogwai.exe --headless --script scripts\VisCache\VisCache_Baselines.py --scene Bistro_Interior.pyscene

REM 1024 spp reference
Mogwai.exe --headless --script scripts\VisCache\VisCache_Reference.py --scene Bistro_Interior.pyscene
```

Output goes to `captures/ablation/` and `captures/baselines/`.

## Troubleshooting

**"Windows SDK not found"** -- Install SDK 10.0.19041.0 specifically via the VS Installer individual components. `windows-latest` GitHub runners lack this SDK; use `windows-2022`.

**Packman download fails** -- Check proxy/firewall settings. Packman downloads CUDA, D3D12 Agility SDK, slang, nvtt, and other binary deps from NVIDIA servers.

**Submodule init errors** -- Falcor's submodules are shallow-cloned because the subtree squash strips `.gitmodules`. The setup script handles this automatically. If you see errors, try:
```bat
git submodule update --init --recursive --depth 1
```

**`.gitmodules` out of sync** -- The pre-commit hook blocks commits if root and `Falcor/.gitmodules` diverge. Fix with:
```bat
bash sync-submodules.sh from-upstream
```

**DXR not available** -- Ensure your GPU driver is up to date. RTX 20xx is the minimum for DXR 1.1. SM 6.5 features (WaveMatch coalescing) require RTX 30xx+.

**Python not found** -- Install Python 3.8+ and ensure it's on PATH. Tests are CPU-only and don't need any GPU libraries.
