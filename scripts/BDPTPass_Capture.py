"""
BDPTPass_Capture.py — Render BDPT and save output EXR for visual verification.

Used to sanity-check that the BDPTPass / ReSTIRBDPTPass port produces sensible
output (not all black, has light transport, has caustics on glass scenes, etc.).

Usage (must run from runtime/, with PROJECT_ROOT set):
    Mogwai.exe --headless -s scripts/BDPTPass_Capture.py

Env vars:
    PASS_KIND      'vanilla' (BDPTPass.dll → "BDPT") | 'restir' (ReSTIRBDPTPass.dll → "ReSTIRBDPT")
    SCENE_FILE     scene basename (e.g. CornellBox_1AreaLight.pyscene)
    NUM_FRAMES     accumulate count (default 64)
    OUT_DIR        output directory (default runtime/captures/bdpt_check/)
"""

import os

try:
    from falcor import *
except ImportError:
    pass

project_root = os.environ.get("PROJECT_ROOT", "")
pass_kind    = os.environ.get("PASS_KIND", "vanilla")  # 'vanilla' | 'restir' | 'caustic'
scene_file   = os.environ.get("SCENE_FILE", "CornellBox_1AreaLight.pyscene")
num_frames   = int(os.environ.get("NUM_FRAMES", "64"))
out_dir      = os.environ.get("OUT_DIR", os.path.join(project_root, "runtime", "captures", "bdpt_check"))

if project_root and not os.path.isabs(scene_file):
    candidate = os.path.join(project_root, "scenes", scene_file)
    if os.path.isfile(candidate):
        scene_file = candidate

os.makedirs(out_dir, exist_ok=True)

# Build graph: VBufferRT → BDPT → AccumulatePass → ToneMapper
g = RenderGraph("BDPTCapture")

if pass_kind == "vanilla":
    bdpt = createPass("BDPT", {})
    label = "vanilla_BDPT"
elif pass_kind == "ptonly":
    # Light subpath count = 0 (useBPT=False). Should match unidirectional
    # path tracing (NEE + camera subpaths only) in expectation. Used as
    # the bias-free baseline test against Falcor's PathTracer.
    bdpt = createPass("BDPT", {'useBPT': False})
    label = "BDPT_ptonly"
elif pass_kind == "caustic":
    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': True,
        'useCausticReservoirs': True,
        'useCausticShift': True,
    })
    label = "ReSTIR_BDPT_caustic"
elif pass_kind == "full":
    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': True,
        'unbiasedTemporalReuse': True,
        'shiftLightPathsToPixelCenters': True,
        'useCausticReservoirs': True,
        'useCausticShift': True,
        'spatialReusePasses': 1,
    })
    label = "ReSTIR_BDPT_full"
else:
    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': True,
        'useCausticReservoirs': False,
        'useCausticShift': False,
    })
    label = "ReSTIR_BDPT"
g.addPass(bdpt, "BDPT")

vbuffer = createPass("VBufferRT", {
    'adjustShadingNormals': False,
    'samplePattern': 'Center',
    'sampleCount': 1,
    'useAlphaTest': True,
})
g.addPass(vbuffer, "VBufferRT")

accum = createPass("AccumulatePass", {'enabled': True, 'precisionMode': 'Single'})
g.addPass(accum, "AccumulatePass")

tm = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
g.addPass(tm, "ToneMapper")

g.addEdge("VBufferRT.vbuffer", "BDPT.vbuffer")
g.addEdge("VBufferRT.viewW",   "BDPT.viewW")
g.addEdge("VBufferRT.mvec",    "BDPT.mvec")
g.addEdge("BDPT.color",        "AccumulatePass.input")
g.addEdge("AccumulatePass.output", "ToneMapper.src")

g.markOutput("AccumulatePass.output")  # capture-target for FrameCapture
g.markOutput("ToneMapper.dst")
m.addGraph(g)

print(f"[bdpt-capture] Loading scene: {scene_file}")
m.loadScene(scene_file)

scene_basename = os.path.splitext(os.path.basename(scene_file))[0]
stem = f"{label}_{scene_basename}_x{num_frames}"

m.frameCapture.outputDir    = out_dir
m.frameCapture.baseFilename = stem

print(f"[bdpt-capture] Rendering {num_frames} accumulated frames, capturing last one...")
# First renderFrame compiles the graph; can't fetch outputs before that.
for i in range(num_frames):
    m.renderFrame()
    if i == num_frames - 1:
        m.frameCapture.capture()

print(f"[bdpt-capture] OK - {stem} saved to {out_dir}")
_HEADLESS_SCRIPT_DONE = True
