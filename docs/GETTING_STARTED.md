# Getting Started

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 (build 19041+) | Windows 11 |
| Visual Studio | 2022 (Desktop C++ workload) | Latest update |
| Windows SDK | 10.0.19041.0 | 10.0.19041.0 (exact) |
| CUDA | 12.x | 12.x |
| GPU | RTX 20xx (DXR 1.1) | RTX 30xx/40xx (SM 6.5, WaveMatch) |
| Python | 3.8+ | 3.10+ |
| Git | 2.43+ | Latest ([git-scm.com](https://git-scm.com)) |

**VS2022 workloads** (via Visual Studio Installer):
- "Desktop development with C++"
- Individual component: "Windows 10 SDK (10.0.19041.0)"

---

## Quickstart (pre-built release)

**One-liner (idempotent — safe to re-run):**

**cmd:**
```bat
curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o %TEMP%\vc-bootstrap.bat && %TEMP%\vc-bootstrap.bat
```

**PowerShell:**
```powershell
curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o "$env:TEMP\vc-bootstrap.bat"; & "$env:TEMP\vc-bootstrap.bat"
```

This clones (or pulls if already cloned), downloads the latest release, fetches test scenes, runs CPU tests + smoke test, and launches Mogwai with Bistro.

**With options (cmd):**

```bat
curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o %TEMP%\vc-bootstrap.bat && %TEMP%\vc-bootstrap.bat --scene Sponza
REM Or after first run:
scripts\bootstrap.bat --scene Sponza --skip-scenes
scripts\quickstart.bat --skip-scenes           &REM skip scene download
scripts\run-tests.bat                          &REM run 43 CPU tests only
scripts\run-tests.bat quick                    &REM convergence tests only (14)
scripts\download_scenes.bat --yes              &REM download all scenes non-interactively
```

**Linux / WSL:**

```bash
# Idempotent: clone or pull
[ -d VisCacheSketch ] && git -C VisCacheSketch pull || git clone https://github.com/ManuelKugelmann/VisCacheSketch.git
cd VisCacheSketch
bash scripts/download_scenes.sh        # interactive scene download
bash scripts/run-tests.sh              # 43 CPU algorithm tests
bash scripts/run-tests.sh quick        # convergence only (14 tests)
```

---

## Build from source

```bash
# Clone (Falcor is included as a subtree — no extra flags needed)
git clone https://github.com/ManuelKugelmann/VisCacheSketch.git
cd VisCacheSketch

# Linux:
./setup.sh

# Windows:
.\setup.bat
```

Each root setup script:
1. Calls Falcor's own setup (submodule init, packman deps, git hooks;
   Windows also generates VS2022 `.sln`)
2. Copies VisCache and ReSTIRPTPass plugins into the Falcor tree
3. Patches CMake to register the plugins
4. Runs CPU unit tests

`Falcor` is a git subtree of the ManuelKugelmann/Falcor fork (Falcor 8.0
with DQLin/ReSTIR_PT ported in). It lives directly in the repo — no submodule
init required.

### Build in Visual Studio

1. Open `Falcor\build\windows-vs2022\Falcor.sln`
2. Set configuration to **Release**, platform to **x64**
3. Build target: **Mogwai**

Or build from command line:

```bat
cmake --preset windows-vs2022-ci
cmake --build build --config Release --target Mogwai
```

### Run

```bat
Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene media\Bistro\Bistro_Interior.pyscene
```

Set `FALCOR_MEDIA_FOLDERS` to avoid full paths:

```bat
set FALCOR_MEDIA_FOLDERS=media
Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene Bistro_Interior.pyscene
```

---

## Using a release

Download from the [Releases page](https://github.com/ManuelKugelmann/VisCacheSketch/releases). Archives are named `viscache-windows-<config>-<sha>.tar.gz`.

```bash
tar xzf viscache-windows-Release-*.tar.gz
Mogwai.exe --script scripts/VisCache/VisCache_Graph.py --scene path/to/Bistro_Interior.pyscene
Mogwai.exe --headless --script scripts/VisCache/VisCache_Graph.py --scene path/to/scene.pyscene
```

### Triggering a manual release

Go to **Actions > Release > Run workflow** on GitHub. The version tag is auto-generated as `dev-YYYYMMDD-HHMMSS-<sha8>`.

---

## Scenes

```bat
scripts\download_scenes.bat              &REM Windows (interactive)
scripts\download_scenes.bat --yes        &REM Windows (download all)
bash scripts/download_scenes.sh          &REM Linux / WSL
```

- **Arcade** — bundled with Falcor (copied automatically)
- **Bistro** (Amazon Lumberyard, ~3.2 GB) — primary benchmark
- **Sponza** (Crytek, ~70 MB) — secondary benchmark
- **VeachAjar** (Bitterli/DQLin, ~62 MB) — ReSTIR PT test scene

---

## Tests

```bat
scripts\run-tests.bat              &REM all 43 tests (convergence + ReSTIR + ablation)
scripts\run-tests.bat quick        &REM convergence tests only (14 tests)
Mogwai.exe --headless --script scripts\VisCache\smoke_test.py   &REM smoke test (requires built Mogwai)
```

---

## Experiments

```bat
REM Ablation captures (10 configs, 200 warmup + 16 capture frames each)
Mogwai.exe --headless --script scripts\VisCache\VisCache_Ablation.py --scene Bistro_Interior.pyscene

REM Baseline captures (14 DI/GI/PT configs)
Mogwai.exe --headless --script scripts\VisCache\VisCache_Baselines.py --scene Bistro_Interior.pyscene

REM 1024 spp reference
Mogwai.exe --headless --script scripts\VisCache\VisCache_Reference.py --scene Bistro_Interior.pyscene
```

Output goes to `captures/ablation/` and `captures/baselines/`.

---

## Submodule sync (subtree workflow)

Two `.gitmodules` files exist (root and `Falcor/.gitmodules`) — the pre-commit hook blocks commits if they diverge. Use `sync-submodules.sh`:

```bash
./sync-submodules.sh from-upstream   # after pulling upstream Falcor
./sync-submodules.sh to-upstream     # before pushing to upstream Falcor
./sync-submodules.sh check           # just check (no changes)
```

---

## Troubleshooting

**"Windows SDK not found"** -- Install SDK 10.0.19041.0 via VS Installer individual components. `windows-latest` GitHub runners lack this SDK; use `windows-2022`.

**Packman download fails** -- Check proxy/firewall. Packman downloads CUDA, D3D12 Agility SDK, slang, nvtt from NVIDIA servers.

**Submodule init errors** -- Setup handles this automatically. If errors persist: `git submodule update --init --recursive --depth 1`

**DXR not available** -- Update GPU driver. RTX 20xx minimum for DXR 1.1. SM 6.5 (WaveMatch) requires RTX 30xx+.

**Python not found** -- Install Python 3.8+ on PATH. Tests are CPU-only.
