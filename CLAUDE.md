# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

VisCacheSketch (VisCache) — Visual Hash Filter for real-time path tracing denoising, built as Falcor render passes.

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

## CI

- Workflow: `.github/workflows/ci.yml`
- Runs on: `ubuntu-22.04` (Linux/GCC), `windows-2022` (VS2022 + Ninja/MSVC)
- Unit tests run first (no GPU needed), then build jobs in parallel

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

## Render Passes

- `Source/RenderPasses/VisHashFilter/` — Visual Hash Filter pass
- `Source/RenderPasses/ReSTIRGIPass/` — ReSTIR GI integration pass
- These get copied into Falcor's source tree during CI build
