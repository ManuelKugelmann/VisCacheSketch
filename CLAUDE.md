# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch (VisCache) — Visibility Cache for real-time path tracing denoising, built as Falcor render passes.

## Project History

See the **History** section at the top of `README.md`. The 2006 Diplomarbeit (`docs/references/Kugelmann2006_ThesisMK.pdf`, referred to as "thesismk") is the direct ancestor of this work — it established CV+RRR, spatial-hash caching, and the shadow ray reduction approach. This project extends that into a real-time system with multilevel hashing and ReSTIR integration.

## Falcor Subtree Policy

- Falcor is in `Falcor/` (added as a git subtree, not a submodule)
- **Keep Falcor files as close to the NVIDIA original as possible.** Do not add project-specific logic (hooks, VisCache paths, etc.) into Falcor's own scripts or source files. All VisCache-specific setup belongs in our root scripts (`setup.sh`, `setup.bat`). This makes subtree pulls/pushes clean and avoids merge conflicts with upstream.
- The only acceptable Falcor modifications are upstream bug fixes or changes needed for the Falcor fork itself (ManuelKugelmann/Falcor)
- Two `.gitmodules` files exist (root and `Falcor/.gitmodules`) — use `sync-submodules.sh` to keep them in sync (see README)

## Build System

- Falcor's internal submodules must be shallow-cloned since subtree squash strips `.gitmodules`
- NVIDIA packman fetches binary dependencies (CUDA, D3D12 Agility SDK, nvtt, slang, etc.)
- After packman pull on Linux, `libnvtt.so.30106` must be copied to `libnvtt.so` (see `Falcor/setup.sh`)
- Root setup scripts (`setup.sh`, `setup.bat`) call Falcor's own setup, then copy VisCache plugins
- CMake presets: `linux-gcc-ci`, `windows-vs2022-ci`, `windows-ninja-msvc-ci`
- Windows builds require SDK 10.0.19041.0 (available on `windows-2022` runner, NOT `windows-latest`)

## Paper Sketch Workflow

- **`viscachepaper/sections/*.md`** are the current WIP paper content. Edit these directly.
- `viscachepaper/paper-sketch.md` is just an index/TOC linking to the section files — not paper content itself.
- CI (`paper.yml`) auto-combines `sections/*.md` (sorted by filename) into `paper-combined.md` and deploys an HTML preview to GitHub Pages.
- **PDF generation** is moving to LaTeX. The old reportlab-based `generate_paper.py` has been removed.
- To show a PDF visually in chat, convert to PNG first:
  ```bash
  pdftoppm -png -r 200 -f 1 -l 1 /tmp/paper.pdf /tmp/page
  # Then Read /tmp/page-1.png
  ```
  Reading a PDF directly with the Read tool parses content but does **not** show a visual image in chat.

## CI

- Workflows (separate, path-scoped triggers):
  - `.github/workflows/paper.yml` — Combines `viscachepaper/sections/*.md` into `paper-combined.md`, deploys to GitHub Pages, comments on PRs (PDF generation preserved but commented out for future TeX publishing)
  - `.github/workflows/validate.yml` — Algorithm validation tests (`tests/`, `Source/RenderPasses/`)
  - `.github/workflows/build.yml` — Binary builds + release (`Source/`, `Falcor/`, `scripts/`, `CMakeLists.txt`, `setup.*`)
- Runs on: `ubuntu-22.04` (Linux/GCC), `windows-2022` (VS2022 + Ninja/MSVC)

## GitHub Interaction from Claude Code Web

`gh` CLI is **not pre-installed** in Claude Code web environments. Use these alternatives:

### Option 1: curl + GitHub REST API (works now, no auth needed for public repos)
```bash
# Check CI status for a commit
curl -s "https://api.github.com/repos/OWNER/REPO/commits/SHA/check-runs" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for cr in data['check_runs']:
    print(f'{cr[\"conclusion\"]:>10}  {cr[\"name\"]}')
"

# View PR details
curl -s "https://api.github.com/repos/OWNER/REPO/pulls/NUMBER"

# List PR check runs
curl -s "https://api.github.com/repos/OWNER/REPO/commits/SHA/check-runs"
```

Note: Unauthenticated GitHub API has a 60 req/hour rate limit per IP.

### Option 2: WebFetch tool
Claude Code's built-in WebFetch can fetch GitHub pages and API endpoints directly.

### Option 3: Install gh via SessionStart hook
Create `.claude/settings.json` with a hook to install gh on session start:
```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup",
      "hooks": [{
        "type": "command",
        "command": "command -v gh || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages focal main' | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt-get update && sudo apt-get install -y gh)"
      }]
    }]
  }
}
```

### Option 4: GitHub MCP Server
Add the GitHub MCP server for structured access:
```bash
claude mcp add --transport http github https://api.githubcopilot.com/mcp/
```

## Workflow

- Work step by step for large edits — break changes into small, incremental Edit calls rather than attempting a single massive Write

## Render Passes

- `Source/RenderPasses/VisCache/` — Visibility Cache pass
- `Source/RenderPasses/ReSTIRPTPass/` — ReSTIR PT pass (DQLin's ReSTIR PT [Lin et al. SIGGRAPH 2022] ported to Falcor 8; supports single-bounce GI with maxBounces=1 and multi-bounce path tracing with higher values)
- These get copied into Falcor's source tree during CI build
