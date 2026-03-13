"""
VisCache_Reference.py  —  1024 spp path tracer reference capture.
Ground truth for MSE/FLIP comparisons against VisCache configurations.

Usage:
    Mogwai.exe --headless --script scripts/VisCache_Reference.py --scene BistroInterior.pyscene

Outputs to: captures/reference/<scenename>/frame_NNNN.exr
"""

import os

kSamplesPerPixel = 1024
kCaptureFrames   = 16
kCaptureDir      = "captures/reference"

# ---------------------------------------------------------------------------
# Build a vanilla path tracer graph (no VisCache, no ReSTIR)
# ---------------------------------------------------------------------------
g = RenderGraph("Reference")

VBuffer = createPass("VBufferRT")
g.addPass(VBuffer, "VBuffer")

PathTracer = createPass("PathTracer", {
    'samplesPerPixel': kSamplesPerPixel,
    'maxSurfaceBounces':      6,
})
g.addPass(PathTracer, "PathTracer")

ToneMapper = createPass("ToneMapper", {
    'autoExposure': False,
    'exposureCompensation': 0.0,
})
g.addPass(ToneMapper, "ToneMapper")

g.addEdge("VBuffer.vbuffer", "PathTracer.vbuffer")
g.addEdge("PathTracer.color", "ToneMapper.src")
g.markOutput("ToneMapper.dst")
g.markOutput("PathTracer.color")   # linear HDR for MSE

m.addGraph(g)

# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------
outdir = os.path.join(kCaptureDir, "ref_1024spp")
os.makedirs(outdir, exist_ok=True)
m.frameCapture.outputDir    = outdir
m.frameCapture.baseFilename = "reference"

print(f"[Reference] Capturing {kCaptureFrames} frames at {kSamplesPerPixel} spp...")

for i in range(kCaptureFrames):
    m.frameCapture.capture()
    renderFrame()

print(f"[Reference] Done — {kCaptureFrames} frames saved to {outdir}")
