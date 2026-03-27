# CornellBox_Base.py — Shared geometry, materials, and camera for all CornellBox variants.
#
# Import from .pyscene files:
#   exec(open("scenes/CornellBox_Base.py" if __file__ else "CornellBox_Base.py").read())
# Then add lights specific to the variant.

# --- Materials ---
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

shiny = StandardMaterial('Shiny')
shiny.baseColor = float4(0.9, 0.9, 0.9, 1.0)
shiny.roughness = 0.15
shiny.metallic = 0.8

pole_mat = StandardMaterial('Pole')
pole_mat.baseColor = float4(0.6, 0.55, 0.5, 1.0)
pole_mat.roughness = 0.8
pole_mat.metallic = 0.0

# --- Helpers ---
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

# --- Room: 2x2x2, floor at Y=0, centered at X=0 Z=0 ---
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

# --- Tall box ---
tall = TriangleMesh.createCube(float3(0.6, 1.2, 0.6))
tall.name = 'TallBox'
tallID = sceneBuilder.addTriangleMesh(tall, white)
tallNode = sceneBuilder.addNode('TallBox', Transform(
    translation=float3(0.35, 0.6, 0.3),
    rotationEulerDeg=float3(0, -15, 0),
))
sceneBuilder.addMeshInstance(tallNode, tallID)

# --- Short box ---
short = TriangleMesh.createCube(float3(0.6, 0.6, 0.6))
short.name = 'ShortBox'
shortID = sceneBuilder.addTriangleMesh(short, white)
shortNode = sceneBuilder.addNode('ShortBox', Transform(
    translation=float3(-0.35, 0.3, -0.2),
    rotationEulerDeg=float3(0, 15, 0),
))
sceneBuilder.addMeshInstance(shortNode, shortID)

# --- Thin diagonal wall on top of short box (light bleeding test) ---
thinwall = TriangleMesh.createCube(float3(0.6, 0.01, 0.6))
thinwall.name = 'ThinWall'
thinwallID = sceneBuilder.addTriangleMesh(thinwall, white)
thinwallNode = sceneBuilder.addNode('ThinWall', Transform(
    translation=float3(-0.35, 0.605, -0.2),
    rotationEulerDeg=float3(0, 60, 0),
))
sceneBuilder.addMeshInstance(thinwallNode, thinwallID)

# --- Sphere ---
sphere = TriangleMesh.createSphere(radius=0.25, segmentsU=48, segmentsV=48)
sphere.name = 'Sphere'
sphereID = sceneBuilder.addTriangleMesh(sphere, shiny)
sphereNode = sceneBuilder.addNode('Sphere', Transform(
    translation=float3(-0.4, 1.1, 0.4),
))
sceneBuilder.addMeshInstance(sphereNode, sphereID)

# --- Tetrahedron cluster ---
import math
tetra = TriangleMesh()
tetra.name = 'Tetrahedron'
s = 0.2
h = s * math.sqrt(2.0/3.0)
v0 = float3( s/2,  -h/2,  -s/(2*math.sqrt(3)))
v1 = float3(-s/2,  -h/2,  -s/(2*math.sqrt(3)))
v2 = float3( 0.0,  -h/2,   s*math.sqrt(3)/2 - s/(2*math.sqrt(3)))
v3 = float3( 0.0,   h/2,   0.0)
def sub(a, b): return float3(a.x-b.x, a.y-b.y, a.z-b.z)
def cross(a, b): return float3(a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x)
def norm(v):
    l = (v.x**2+v.y**2+v.z**2)**0.5
    return float3(v.x/l, v.y/l, v.z/l) if l>0 else float3(0,1,0)
uv = float2(0,0)
n = norm(cross(sub(v2,v0), sub(v1,v0)))
i = tetra.addVertex(v0, n, uv); tetra.addVertex(v2, n, uv); tetra.addVertex(v1, n, uv)
tetra.addTriangle(i, i+1, i+2)
n = norm(cross(sub(v1,v0), sub(v3,v0)))
i = tetra.addVertex(v0, n, uv); tetra.addVertex(v1, n, uv); tetra.addVertex(v3, n, uv)
tetra.addTriangle(i, i+1, i+2)
n = norm(cross(sub(v2,v1), sub(v3,v1)))
i = tetra.addVertex(v1, n, uv); tetra.addVertex(v2, n, uv); tetra.addVertex(v3, n, uv)
tetra.addTriangle(i, i+1, i+2)
n = norm(cross(sub(v0,v2), sub(v3,v2)))
i = tetra.addVertex(v2, n, uv); tetra.addVertex(v0, n, uv); tetra.addVertex(v3, n, uv)
tetra.addTriangle(i, i+1, i+2)
tetraID = sceneBuilder.addTriangleMesh(tetra, white)

import random
random.seed(42)
cx, cy, cz = 0.5, 0.35, -0.45
cluster_r = 0.25
for idx in range(15):
    while True:
        dx = random.uniform(-1, 1)
        dy = random.uniform(-1, 1)
        dz = random.uniform(-1, 1)
        if dx*dx + dy*dy + dz*dz <= 1.0:
            break
    tx = cx + dx * cluster_r
    ty = max(0.1, cy + dy * cluster_r)
    tz = cz + dz * cluster_r
    node = sceneBuilder.addNode(f'Tetra_{idx}', Transform(
        translation=float3(tx, ty, tz),
        rotationEulerDeg=float3(random.uniform(120,220), random.uniform(-90,90), random.uniform(-20,20)),
        scaling=float3(*([random.uniform(0.4,0.9)]*3)),
    ))
    sceneBuilder.addMeshInstance(node, tetraID)

# --- Poles ---
pole_mesh = TriangleMesh.createCube(float3(0.03, 1.4, 0.03))
pole_mesh.name = 'Pole'
poleID = sceneBuilder.addTriangleMesh(pole_mesh, pole_mat)
short_pole = TriangleMesh.createCube(float3(0.03, 0.6, 0.03))
short_pole.name = 'ShortPole'
shortPoleID = sceneBuilder.addTriangleMesh(short_pole, pole_mat)
for idx, (tx, ty, tz, rx, ry, rz, mid) in enumerate([
    ( 0.0,  0.7, -0.6,   25,  15,   0, poleID),
    ( 0.15, 0.7, -0.5,  -20, -10,  30, poleID),
    (-0.1,  0.7, -0.55,  15,  40, -15, poleID),
    ( 0.05, 0.7, -0.45, -30,  25,  10, poleID),
    ( 0.0,  0.08, -0.5,   85,  20,   0, shortPoleID),
    ( 0.1,  0.12, -0.4,   92, -35,   0, shortPoleID),
]):
    node = sceneBuilder.addNode(f'Pole_{idx}', Transform(
        translation=float3(tx, ty, tz),
        rotationEulerDeg=float3(rx, ry, rz),
    ))
    sceneBuilder.addMeshInstance(node, mid)

# --- Camera (zoomed to fill square frame) ---
camera = Camera('CornellBoxCam')
camera.position = float3(0.0, 1.0, -2.8)
camera.target   = float3(0.0, 1.0, 0.0)
camera.up       = float3(0.0, 1.0, 0.0)
camera.focalLength = 28.0
sceneBuilder.addCamera(camera)
