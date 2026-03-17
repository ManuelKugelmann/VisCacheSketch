"""
validate_scripts.py — Validate Python graph/capture scripts without GPU.

Two levels of validation:
  1. py_compile: Syntax check all .py files in scripts/
  2. Mock-import: Execute graph scripts with mocked Falcor globals to verify
     they construct render graphs without crashing.

Usage:
    python scripts/validate_scripts.py           # run both checks
    python scripts/validate_scripts.py syntax     # syntax only
    python scripts/validate_scripts.py import     # mock-import only

Exit code 0 = all OK, 1 = failures found.
"""

import os
import sys
import py_compile
import types
import importlib.util

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. Syntax check — py_compile every .py in scripts/
# ---------------------------------------------------------------------------

# Scripts that use Mogwai top-level globals at module scope — these need
# mock-import (check 2) but are also syntax-checked here.
ALL_SCRIPTS = sorted(
    f for f in os.listdir(SCRIPT_DIR)
    if f.endswith(".py") and f != os.path.basename(__file__)
)


def check_syntax():
    """Return list of (filename, error_msg) for scripts that fail py_compile."""
    failures = []
    for fname in ALL_SCRIPTS:
        path = os.path.join(SCRIPT_DIR, fname)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            failures.append((fname, str(e)))
    return failures


# ---------------------------------------------------------------------------
# 2. Mock-import — execute graph scripts with fake Falcor globals
# ---------------------------------------------------------------------------

# Graph scripts that call render_graph_*() at module level via m.addGraph().
# These are the primary targets for mock-import validation.
GRAPH_SCRIPTS = [
    "MinimalPathTracer_Graph.py",
    "MinimalPathTracer_VisCache_Graph.py",
    "PathTracer_Graph.py",
    "PathTracer_VisCache_Graph.py",
    "RTXDI_Graph.py",
    "RTXDI_VisCache_Graph.py",
    "ReSTIRPT_Graph.py",
    "ReSTIRPT_VisCache_Graph.py",
]


class _MockPass:
    """Mock render pass returned by createPass()."""
    def __init__(self, pass_type, params=None):
        self._type = pass_type
        self._params = params or {}

    def __getattr__(self, name):
        return None

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            pass  # silently accept any property set


class _MockGraph:
    """Mock RenderGraph — records passes and edges for structural validation."""
    def __init__(self, name=""):
        self.name = name
        self.passes = {}
        self.edges = []
        self.outputs = []

    def addPass(self, p, name):
        self.passes[name] = p

    def addEdge(self, src, dst):
        self.edges.append((src, dst))

    def markOutput(self, name):
        self.outputs.append(name)

    def getPass(self, name):
        return self.passes.get(name, _MockPass("unknown"))

    def removeGraph(self, g):
        pass


class _MockFrameCapture:
    outputDir = ""
    baseFilename = ""
    def capture(self):
        pass


class _MockScene:
    class _Cam:
        position = None
        target = None
    camera = _Cam()


class _MockMogwai:
    """Mock for the global `m` (Mogwai app instance)."""
    frameCapture = _MockFrameCapture()
    scene = _MockScene()
    graphs = []

    def addGraph(self, g):
        self.graphs.append(g)

    def removeGraph(self, g):
        pass

    def loadScene(self, path):
        pass


class _MockFloat3:
    def __init__(self, *args):
        self.x = args[0] if len(args) > 0 else 0
        self.y = args[1] if len(args) > 1 else 0
        self.z = args[2] if len(args) > 2 else 0


def _make_mock_builtins():
    """Return dict of Falcor globals to inject into script execution."""
    return {
        "RenderGraph": _MockGraph,
        "createPass": _MockPass,
        "renderFrame": lambda: None,
        "m": _MockMogwai(),
        "float3": _MockFloat3,
    }


def check_imports():
    """Mock-import graph scripts and return list of (filename, error_msg) for failures."""
    failures = []

    for fname in GRAPH_SCRIPTS:
        path = os.path.join(SCRIPT_DIR, fname)
        if not os.path.exists(path):
            failures.append((fname, "file not found"))
            continue

        try:
            # Build a module with Falcor globals injected
            spec = importlib.util.spec_from_file_location(
                fname.replace(".py", ""), path
            )
            mod = importlib.util.module_from_spec(spec)

            # Inject Falcor globals into module namespace
            for k, v in _make_mock_builtins().items():
                setattr(mod, k, v)

            # Also inject into builtins so nested `from X import Y` works
            # when X uses top-level globals
            import builtins
            saved = {}
            mock_builtins = _make_mock_builtins()
            for k, v in mock_builtins.items():
                saved[k] = getattr(builtins, k, None)
                setattr(builtins, k, v)

            try:
                spec.loader.exec_module(mod)
            finally:
                # Restore builtins
                for k, v in saved.items():
                    if v is None:
                        try:
                            delattr(builtins, k)
                        except AttributeError:
                            pass
                    else:
                        setattr(builtins, k, v)

        except Exception as e:
            failures.append((fname, f"{type(e).__name__}: {e}"))

    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    ok = True

    if mode in ("all", "syntax"):
        print("=== Python syntax check (py_compile) ===")
        fails = check_syntax()
        if fails:
            for fname, err in fails:
                print(f"  FAIL: {fname}\n        {err}")
            ok = False
        else:
            print(f"  OK: {len(ALL_SCRIPTS)} scripts passed syntax check")
        print()

    if mode in ("all", "import"):
        print("=== Mock-import check (graph construction) ===")
        fails = check_imports()
        if fails:
            for fname, err in fails:
                print(f"  FAIL: {fname}\n        {err}")
            ok = False
        else:
            print(f"  OK: {len(GRAPH_SCRIPTS)} graph scripts passed mock-import")
        print()

    if not ok:
        print("FAILED — see errors above.")
        sys.exit(1)
    else:
        print("All script validation checks passed.")


if __name__ == "__main__":
    main()
