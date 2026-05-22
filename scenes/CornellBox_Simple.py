# CornellBox_Simple.py — Minimal Cornell box without the tall-box / thin-wall /
# tetra / pole clutter from CornellBox_Base.py. Designed as a simple, clean
# baseline for BDPT vs PT comparisons. Variant pyscene files add a light and
# (optionally) a single test object (glass ball, glass pane, slit wall, etc.).

# Materials
white = StandardMaterial('White')
white.baseColor = float4(0.73, 0.73, 0.73, 1.0)
white.roughness = 1.0
white.metallic = 0.0

red = StandardMaterial('Red')
red.baseColor = float4(0.65, 0.05, 0.05, 1.0)
red.roughness = 1.0
red.metallic = 0.0

green = StandardMaterial('Green')
green.baseColor = float4(0.12, 0.45, 0.15, 1.0)
green.roughness = 1.0
green.metallic = 0.0

# Quad helper
def addQuad(name, mat, p0, p1, p2, p3, nx, ny, nz):
    m = TriangleMesh()
    m.name = name
    n = float3(nx, ny, nz)
    m.addVertex(p0, n, float2(0, 0))
    m.addVertex(p1, n, float2(1, 0))
    m.addVertex(p2, n, float2(1, 1))
    m.addVertex(p3, n, float2(0, 1))
    m.addTriangle(0, 1, 2)
    m.addTriangle(0, 2, 3)
    meshID = sceneBuilder.addTriangleMesh(m, mat)
    nodeID = sceneBuilder.addNode(name)
    sceneBuilder.addMeshInstance(nodeID, meshID)

# Room — 2x2x2, floor at Y=0, centered at X=0 Z=0
L, R = -1.0, 1.0
B, T =  0.0, 2.0
Bk   =  1.0
Fr   = -1.0

addQuad('Floor', white,
    float3(L, B, Bk), float3(R, B, Bk), float3(R, B, Fr), float3(L, B, Fr), 0, 1, 0)
addQuad('Ceiling', white,
    float3(L, T, Fr), float3(R, T, Fr), float3(R, T, Bk), float3(L, T, Bk), 0, -1, 0)
addQuad('BackWall', white,
    float3(R, B, Bk), float3(L, B, Bk), float3(L, T, Bk), float3(R, T, Bk), 0, 0, -1)
addQuad('LeftWall', red,
    float3(L, B, Fr), float3(L, B, Bk), float3(L, T, Bk), float3(L, T, Fr), 1, 0, 0)
addQuad('RightWall', green,
    float3(R, B, Bk), float3(R, B, Fr), float3(R, T, Fr), float3(R, T, Bk), -1, 0, 0)

# Camera
camera = Camera('CornellBoxCam')
camera.position = float3(0.0, 1.0, -3.6)
camera.target   = float3(0.0, 1.0, 0.0)
camera.up       = float3(0.0, 1.0, 0.0)
camera.focalLength = 28.0
sceneBuilder.addCamera(camera)
