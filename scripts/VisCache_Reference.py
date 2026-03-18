"""
VisCache_Reference.py  —  High-spp path tracer reference capture.
Ground truth for MSE/FLIP comparisons against VisCache configurations.

Usage:
    Mogwai.exe --headless --script scripts/VisCache_Reference.py --scene BistroInterior.pyscene

Outputs to: captures/reference/<scenename>/frame_NNNN.exr

Note: PathTracer.samplesPerPixel max is 16. To get 1024 effective spp,
we accumulate 64 frames x 16 spp each (64 * 16 = 1024).
"""

import os

kSppPerFrame     = 16     # PathTracer max spp per frame
kAccumFrames     = 64     # frames to accumulate (64 * 16 = 1024 effective spp)
kCaptureFrames   = 16     # reference frames to capture (each after full accumulation)
kCaptureDir      = "captures/reference"

# ---------------------------------------------------------------------------
# Build a vanilla path tracer graph (no VisCache, no ReSTIR) with accumulation
# ---------------------------------------------------------------------------
g = RenderGraph("Reference")

VBuffer = createPass("VBufferRT")
g.addPass(VBuffer, "VBuffer")

PathTracer = createPass("PathTracer", {
    'samplesPerPixel':    kSppPerFrame,
    'maxSurfaceBounces':  6,
})
g.addPass(PathTracer, "PathTracer")

Accum = createPass("AccumulatePass", {
    'enabled':        True,
    'precisionMode':  "Single",
})
g.addPass(Accum, "AccumulatePass")

ToneMapper = createPass("ToneMapper", {
    'autoExposure':          False,
    'exposureCompensation':  0.0,
})
g.addPass(ToneMapper, "ToneMapper")

g.addEdge("VBuffer.vbuffer",       "PathTracer.vbuffer")
g.addEdge("PathTracer.color",      "AccumulatePass.input")
g.addEdge("AccumulatePass.output", "ToneMapper.src")
g.markOutput("ToneMapper.dst")
g.markOutput("AccumulatePass.output")   # linear HDR for MSE

m.addGraph(g)

# ---------------------------------------------------------------------------
# Capture — render warmup then capture
# ---------------------------------------------------------------------------
outdir = os.path.join(kCaptureDir, "ref_1024spp")
os.makedirs(outdir, exist_ok=True)
m.frameCapture.outputDir    = outdir
m.frameCapture.baseFilename = "reference"

print(f"[Reference] Capturing {kCaptureFrames} frames at {kSppPerFrame * kAccumFrames} effective spp...")

# Render a warmup frame to compile the graph
renderFrame()

for i in range(kCaptureFrames):
    # Accumulate frames for high spp
    for _ in range(kAccumFrames - 1):
        renderFrame()
    m.frameCapture.capture()
    renderFrame()

print(f"[Reference] Done — {kCaptureFrames} frames saved to {outdir}")
