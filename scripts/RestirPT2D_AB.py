"""
RestirPT2D_AB.py — A/B EXR capture: vanilla PathTracer vs restirpt_2d.

Sets _HEADLESS_SCRIPT_DONE=True so the harness doesn't try to load scene
itself; we drive scene loading + frame rendering + capture per variant.

Usage (headless):
    .scripts/mogwai-headless.sh 'RestirPT2D_AB.py' Sponza 32

Outputs:
    runtime/captures/restirpt2d_ab/<scene>/{vanilla,restirpt_2d}_x<N>.<output>.<idx>.exr
"""
import os, sys

try:
    from falcor import *
except ImportError:
    pass

_HEADLESS_SCRIPT_DONE = True   # tell the harness we drive everything

NUM_FRAMES = int(os.environ.get("AB_FRAMES", "32"))   # don't conflict with NUM_FRAMES env that the harness sets
SCENE_FILE = os.environ.get("SCENE_FILE", "CornellBox_1AreaLight.pyscene")
PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "")
SCENE_NAME = os.path.splitext(os.path.basename(SCENE_FILE))[0]
OUT_DIR = os.path.join("captures", "restirpt2d_ab", SCENE_NAME)


def make_graph(variant: str, name: str):
    """variant: 'vanilla' | 'rpt2d' | 'dqlin'"""
    g = RenderGraph(name)

    if variant == "dqlin":
        # Mirror the canonical ReSTIRPT_Graph config: GBufferRT → RTXDIPass
        # (direct) → ReSTIRPTPass (indirect, fed by RTXDI direct).
        gbuf = createPass("GBufferRT", {"samplePattern": "Stratified", "sampleCount": 1})
        g.addPass(gbuf, "GBufferRT")
        rtxdi = createPass("RTXDIPass", {
            "options": {
                "mode":                       "NoResampling",
                "localLightCandidateCount":    8,
                "infiniteLightCandidateCount": 1,
            },
        })
        g.addPass(rtxdi, "RTXDIPass")
        restirpt = createPass("ReSTIRPTPass", {
            "samplesPerPixel":             1,
            "maxSurfaceBounces":           3,
            "useDirectLighting":           True,
            "disableDirectIllumination":   True,    # RTXDI feeds direct
            "pathSamplingMode":            "ReSTIR",
            "fireflyClampK":               100.0,    # bound the RIS estimator
        })
        g.addPass(restirpt, "ReSTIRPTPass")
        accum = createPass("AccumulatePass", {"enabled": True, "precisionMode": "Single"})
        g.addPass(accum, "AccumulatePass")
        tone = createPass("ToneMapper", {"autoExposure": False, "exposureValue": 0.0, "operator": "Aces"})
        g.addPass(tone, "ToneMapper")
        g.addEdge("GBufferRT.vbuffer",      "RTXDIPass.vbuffer")
        g.addEdge("GBufferRT.mvec",         "RTXDIPass.mvec")
        g.addEdge("RTXDIPass.color",        "ReSTIRPTPass.directLighting")
        g.addEdge("GBufferRT.vbuffer",      "ReSTIRPTPass.vbuffer")
        g.addEdge("GBufferRT.mvec",         "ReSTIRPTPass.motionVectors")
        g.addEdge("ReSTIRPTPass.color",     "AccumulatePass.input")
        g.addEdge("AccumulatePass.output",  "ToneMapper.src")
        g.markOutput("ToneMapper.dst")
        g.markOutput("AccumulatePass.output")
        return g

    # vanilla / rpt2d — both use Falcor's PathTracer plugin.
    vbuf = createPass("VBufferRT", {"samplePattern": "Stratified", "sampleCount": 16})
    g.addPass(vbuf, "VBufferRT")
    pt = createPass("PathTracer", {
        "samplesPerPixel":   1,
        "maxSurfaceBounces": 3,
        "colorFormat":       "LogLuvHDR",
        "useRestirPT":       (variant == "rpt2d"),
    })
    g.addPass(pt, "PathTracer")
    accum = createPass("AccumulatePass", {"enabled": True, "precisionMode": "Single"})
    g.addPass(accum, "AccumulatePass")
    tone = createPass("ToneMapper", {"autoExposure": False, "exposureValue": 0.0, "operator": "Aces"})
    g.addPass(tone, "ToneMapper")
    g.addEdge("VBufferRT.vbuffer",     "PathTracer.vbuffer")
    g.addEdge("VBufferRT.viewW",       "PathTracer.viewW")
    g.addEdge("PathTracer.color",      "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")
    return g


def render_and_capture(variant: str, tag: str):
    print(f"[ab] === {tag} ===")
    # Build + activate this graph
    g = make_graph(variant, tag)
    m.addGraph(g)

    # Scene path resolution (mirror RunGraphHeadless logic)
    scene_path = SCENE_FILE
    if PROJECT_ROOT and not os.path.isabs(scene_path):
        cand = os.path.join(PROJECT_ROOT, "scenes", scene_path)
        if os.path.isfile(cand):
            scene_path = cand
    print(f"[ab] Loading scene: {scene_path}")
    m.loadScene(scene_path)
    m.resizeFrameBuffer(512, 512)   # match ladder GT resolution

    # Accumulate
    print(f"[ab] Rendering {NUM_FRAMES} frames...")
    for i in range(NUM_FRAMES):
        m.renderFrame()

    # Capture both outputs (post-tonemap LDR + pre-tonemap HDR)
    out_path = os.path.join(PROJECT_ROOT or ".", OUT_DIR) if PROJECT_ROOT else OUT_DIR
    os.makedirs(out_path, exist_ok=True)
    m.frameCapture.outputDir    = out_path
    m.frameCapture.baseFilename = f"{tag}_x{NUM_FRAMES}"
    m.frameCapture.capture()
    print(f"[ab] Captured to {out_path}")

    # Remove graph for next iteration
    m.removeGraph(g)


render_and_capture(variant="vanilla", tag="vanilla")
render_and_capture(variant="rpt2d",   tag="restirpt_2d")
if os.environ.get("AB_DQLIN", "0") == "1":
    render_and_capture(variant="dqlin", tag="restirpt_dqlin")
print("[ab] DONE")
