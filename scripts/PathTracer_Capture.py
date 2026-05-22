"""
PathTracer_Capture.py — Render Falcor's vanilla PathTracer and save EXR/PNG.
Reference baseline for comparing against BDPTPass / ReSTIRBDPTPass.
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

if project_root and not os.path.isabs(scene_file):
    candidate = os.path.join(project_root, "scenes", scene_file)
    if os.path.isfile(candidate):
        scene_file = candidate

os.makedirs(out_dir, exist_ok=True)

g = RenderGraph("PathTracerCapture")

# PT config (bounce budget + emissive sampler) selectable via env vars
# so we can do matched comparisons against BDPT at the same bounce count.
pt_bounces = int(os.environ.get("PT_BOUNCES", "20"))
pt = createPass("PathTracer", {
    'samplesPerPixel': 1,
    'maxSurfaceBounces': pt_bounces,
    'maxDiffuseBounces': pt_bounces,
    'maxSpecularBounces': pt_bounces,
    'maxTransmissionBounces': pt_bounces,
    'emissiveSampler': "Power",
})
g.addPass(pt, "PathTracer")

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

g.addEdge("VBufferRT.vbuffer", "PathTracer.vbuffer")
g.addEdge("VBufferRT.viewW",   "PathTracer.viewW")
g.addEdge("VBufferRT.mvec",    "PathTracer.mvec")
g.addEdge("PathTracer.color",  "AccumulatePass.input")
g.addEdge("AccumulatePass.output", "ToneMapper.src")

g.markOutput("AccumulatePass.output")
g.markOutput("ToneMapper.dst")
m.addGraph(g)

print(f"[pt-capture] Loading scene: {scene_file}")
m.loadScene(scene_file)

scene_basename = os.path.splitext(os.path.basename(scene_file))[0]
stem = f"PathTracer_b{pt_bounces}_{scene_basename}_x{num_frames}"

m.frameCapture.outputDir    = out_dir
m.frameCapture.baseFilename = stem

print(f"[pt-capture] Rendering {num_frames} accumulated frames, capturing last one...")
for i in range(num_frames):
    m.renderFrame()
    if i == num_frames - 1:
        m.frameCapture.capture()

print(f"[pt-capture] OK - {stem} saved to {out_dir}")
_HEADLESS_SCRIPT_DONE = True
