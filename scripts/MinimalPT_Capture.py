"""
MinimalPT_Capture.py — Capture Falcor's MinimalPathTracer for independent
ground-truth reference. Used as a third-party check when validating
whether BDPTPass or Falcor PathTracer has the right mean radiance.
"""
import os

try:
    from falcor import *
except ImportError:
    pass

project_root = os.environ.get("PROJECT_ROOT", "")
scene_file   = os.environ.get("SCENE_FILE", "CornellBox_1AreaLight.pyscene")
num_frames   = int(os.environ.get("NUM_FRAMES", "64"))
out_dir      = os.environ.get("OUT_DIR", os.path.join(project_root, "runtime", "captures", "bdpt_check"))
mpt_bounces  = int(os.environ.get("MPT_BOUNCES", "20"))

if project_root and not os.path.isabs(scene_file):
    candidate = os.path.join(project_root, "scenes", scene_file)
    if os.path.isfile(candidate):
        scene_file = candidate

os.makedirs(out_dir, exist_ok=True)

g = RenderGraph("MPTCapture")

mpt = createPass("MinimalPathTracer", {'maxBounces': mpt_bounces})
g.addPass(mpt, "MinimalPathTracer")

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

g.addEdge("VBufferRT.vbuffer", "MinimalPathTracer.vbuffer")
g.addEdge("VBufferRT.viewW",   "MinimalPathTracer.viewW")
g.addEdge("MinimalPathTracer.color",  "AccumulatePass.input")
g.addEdge("AccumulatePass.output", "ToneMapper.src")

g.markOutput("AccumulatePass.output")
g.markOutput("ToneMapper.dst")
m.addGraph(g)

print(f"[mpt-capture] Loading scene: {scene_file}")
m.loadScene(scene_file)

scene_basename = os.path.splitext(os.path.basename(scene_file))[0]
stem = f"MPT_b{mpt_bounces}_{scene_basename}_x{num_frames}"

m.frameCapture.outputDir    = out_dir
m.frameCapture.baseFilename = stem

print(f"[mpt-capture] Rendering {num_frames} frames...")
for i in range(num_frames):
    m.renderFrame()
    if i == num_frames - 1:
        m.frameCapture.capture()

print(f"[mpt-capture] OK - {stem} saved to {out_dir}")
_HEADLESS_SCRIPT_DONE = True
