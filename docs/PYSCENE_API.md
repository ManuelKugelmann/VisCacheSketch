# Falcor 8 .pyscene API Reference

Falcor scene files (`.pyscene`) are Python scripts executed by Mogwai at load time.
A global `sceneBuilder` object is available for constructing scenes.

> Source: pybind11 bindings in `Falcor/Source/Falcor/Scene/` (SceneBuilder.cpp, Camera.cpp, Light.cpp, Material.cpp, etc.)
>
> Reference scenes: [SirKero/RTProgressivePhotonMapper](https://github.com/SirKero/RTProgressivePhotonMapper) `Scenes/` — Bistro (emissive+glass+volumeAbsorption), caustic glass (spotlight), livingRoom (PBRT import, tinted glass), veachBiDir, waterCaustic

---

## SceneBuilder

The `sceneBuilder` global is the entry point for all scene construction.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `envMap` | `EnvMap` | Get/set environment map |
| `renderSettings` | `RenderSettings` | Get/set render settings |
| `selectedCamera` | `Camera` | Get/set active camera |
| `cameraSpeed` | `float` | Camera movement speed |
| `flags` | `SceneBuilderFlags` | Read-only build flags |
| `materials` | list | Read-only material list |
| `lights` | list | Read-only light list |
| `cameras` | list | Read-only camera list |
| `animations` | list | Read-only animation list |

### Methods

```python
# Import a scene file (FBX, OBJ, glTF, USD, etc.)
sceneBuilder.importScene('path/to/file.fbx')
sceneBuilder.importScene('path/to/file.fbx', {'key': 'value'})  # with import options

# Materials
sceneBuilder.addMaterial(material)
sceneBuilder.getMaterial('MaterialName')           # get existing by name
sceneBuilder.replaceMaterial(original, replacement)
sceneBuilder.loadMaterialTexture(material, slot, 'path/to/tex.png')
sceneBuilder.waitForMaterialTextureLoading()

# Lights
sceneBuilder.addLight(light)
sceneBuilder.getLight('LightName')

# Camera
sceneBuilder.addCamera(camera)

# Scene graph
nodeID = sceneBuilder.addNode('name', transform)                # root node
nodeID = sceneBuilder.addNode('name', transform, parentNodeID)  # child node

# Mesh instances (low-level, per-mesh construction)
meshID = sceneBuilder.addTriangleMesh(triangleMesh, material)
meshID = sceneBuilder.addTriangleMesh(triangleMesh, material, isAnimated=True)
sceneBuilder.addMeshInstance(meshID, nodeID)

# SDF grids
sdfID = sceneBuilder.addSDFGrid(sdfGrid, material)
sceneBuilder.addSDFGridInstance(sdfID, nodeID)

# Animation
sceneBuilder.addAnimation(animation)
sceneBuilder.createAnimation(animatable, 'name', duration)

# Other
sceneBuilder.addCustomPrimitive(...)
sceneBuilder.loadLightProfile('filename.ies', normalize=True)
```

---

## Camera

```python
camera = Camera('name')          # name is optional
```

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | `str` | `""` | Camera name |
| `position` | `float3` | — | World position |
| `target` | `float3` | — | Look-at target |
| `up` | `float3` | — | Up vector |
| `focalLength` | `float` | `21.0` | Focal length in mm |
| `focalDistance` | `float` | `1.0` | Focus distance (for DoF) |
| `apertureRadius` | `float` | `0.0` | Aperture radius (0 = pinhole) |
| `frameHeight` | `float` | — | Sensor height in mm |
| `frameWidth` | `float` | — | Sensor width in mm |
| `aspectRatio` | `float` | — | Width / height |
| `nearPlane` | `float` | `0.1` | Near clip |
| `farPlane` | `float` | `1000` | Far clip |
| `shutterSpeed` | `float` | — | For motion blur |
| `ISOSpeed` | `float` | — | ISO sensitivity |

---

## Lights

### DirectionalLight

```python
light = DirectionalLight('name')
light.intensity = float3(1.0, 0.77, 0.54)   # RGB radiance
light.direction = float3(0.6, -0.7, -0.3)    # world-space direction
```

### PointLight

```python
light = PointLight('name')
light.intensity = float3(0.9, 2.4, 3.0)
light.position  = float3(-2.87, 2.0, 2.99)
light.direction = float3(0, -1, 0)           # for spot lights
light.openingAngle  = 3.14                    # half-angle in radians (default = pi = omni)
light.penumbraAngle = 0.0                     # soft edge in radians
```

### DistantLight

```python
light = DistantLight('name')
light.direction = float3(0, -1, 0)
light.angle     = 0.0                         # angular extent in radians (0 = point)
```

### Area Lights

```python
light = RectLight('name')    # rectangular area light
light = DiscLight('name')    # disc area light
light = SphereLight('name')  # sphere area light
```

All area lights inherit from `AnalyticAreaLight` and support `intensity`, `name`, `active`, `animated`.

### Common Light Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Light name |
| `active` | `bool` | Enable/disable |
| `animated` | `bool` | Whether light is animated |
| `intensity` | `float3` | RGB intensity/radiance |

---

## EnvMap

```python
envMap = EnvMap('path/to/environment.hdr')
envMap.intensity = 1.0           # scalar multiplier
envMap.rotation  = float3(0,0,0) # Euler rotation in radians
envMap.tint      = float3(1,1,1) # RGB tint
sceneBuilder.envMap = envMap
```

| Property | Type | Description |
|----------|------|-------------|
| `path` | `str` | Read-only, source file path |
| `intensity` | `float` | Brightness multiplier |
| `rotation` | `float3` | Euler rotation (radians) |
| `tint` | `float3` | RGB color tint |

---

## Material (StandardMaterial)

```python
mat = Material('name')           # creates StandardMaterial (MetalRough model)
# or
mat = Material('name', ShadingModel.SpecGloss)
```

### Base Properties (all material types)

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Material name |
| `type` | enum | Read-only material type |
| `doubleSided` | `bool` | Two-sided rendering |
| `thinSurface` | `bool` | Thin surface model |
| `emissive` | `bool` | Read-only, has emissive |
| `alphaMode` | enum | Alpha testing mode |
| `alphaThreshold` | `float` | Alpha cutoff |
| `nestedPriority` | `int` | Priority for nested dielectrics |
| `textureTransform` | `Transform` | UV transform |

### BasicMaterial Properties (StandardMaterial, ClothMaterial, HairMaterial)

| Property | Type | Description |
|----------|------|-------------|
| `baseColor` | `float4` | RGBA base color |
| `specularParams` | `float4` | Specular parameters |
| `transmissionColor` | `float3` | Volume transmission tint |
| `diffuseTransmission` | `float` | Diffuse transmission weight |
| `specularTransmission` | `float` | Specular transmission (0 = opaque, 1 = glass) |
| `volumeAbsorption` | `float3` | Volume absorption coefficient |
| `volumeScattering` | `float3` | Volume scattering coefficient |
| `volumeAnisotropy` | `float` | Henyey-Greenstein anisotropy |
| `indexOfRefraction` | `float` | IOR (glass ~1.5) |
| `displacementScale` | `float` | Displacement mapping scale |
| `displacementOffset` | `float` | Displacement mapping offset |

### StandardMaterial-Specific Properties

| Property | Type | Description |
|----------|------|-------------|
| `roughness` | `float` | Surface roughness (0 = mirror, 1 = diffuse) |
| `metallic` | `float` | Metalness (0 = dielectric, 1 = metal) |
| `emissiveColor` | `float3` | RGB emissive color |
| `emissiveFactor` | `float` | Emissive intensity multiplier |
| `shadingModel` | enum | Read-only (MetalRough or SpecGloss) |

### Texture Loading

```python
mat.loadTexture(MaterialTextureSlot.BaseColor, 'textures/albedo.png')
mat.loadTexture(MaterialTextureSlot.Normal, 'textures/normal.png')
mat.loadTexture(MaterialTextureSlot.Specular, 'textures/roughness.png')
mat.clearTexture(MaterialTextureSlot.Emissive)
```

**MaterialTextureSlot** values: `BaseColor`, `Specular`, `Emissive`, `Normal`, `Transmission`, `Displacement`, `Index`

### Other Material Types

- `ClothMaterial('name')` — fabric/cloth BRDF (+ `roughness`)
- `HairMaterial('name')` — hair/fur BCSDF
- `MERLMaterial('name', 'path')` — measured BRDF
- `MERLMixMaterial('name', ['path1', 'path2'])` — blended measured BRDFs
- `RGLMaterial('name', 'path')` — glinty/RGL material
- PBRT materials: `PBRTDiffuseMaterial`, `PBRTConductorMaterial`, `PBRTCoatedConductorMaterial`, `PBRTDielectricMaterial`, `PBRTCoatedDiffuseMaterial`, `PBRTDiffuseTransmissionMaterial`

---

## Transform

```python
xform = Transform()
xform.translation    = float3(x, y, z)
xform.rotationEuler  = float3(rx, ry, rz)       # radians
xform.rotationEulerDeg = float3(rx, ry, rz)      # degrees
xform.scaling        = float3(sx, sy, sz)
xform.order          = CompositionOrder.ScaleRotateTranslate  # default
xform.lookAt(position, target, up)
matrix = xform.matrix                             # read-only 4x4
```

---

## TriangleMesh

```python
# Load from file
mesh = TriangleMesh.createFromFile('path/to/model.obj')
mesh = TriangleMesh.createFromFile('path/to/model.obj', smoothNormals=True)

# Procedural primitives
mesh = TriangleMesh.createQuad(size=float2(1, 1))
mesh = TriangleMesh.createDisk(radius=1.0, segments=32)
mesh = TriangleMesh.createCube(size=float3(1, 1, 1))
mesh = TriangleMesh.createSphere(radius=1.0, segmentsU=32, segmentsV=32)

# Manual construction
mesh = TriangleMesh()
mesh.addVertex(position=float3(...), normal=float3(...), texCoord=float2(...))
mesh.addTriangle(i0=0, i1=1, i2=2)
```

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Mesh name |
| `frontFaceCW` | `bool` | Clockwise front face winding |
| `vertices` | list | Read-only vertex list |
| `indices` | list | Read-only index list |

---

## Animation

```python
anim = Animation('name', nodeID, duration)  # duration in seconds
anim.addKeyframe(time, transform)           # time in seconds

anim.preInfinityBehavior  = Animation.Behavior.Constant   # or Linear, Cycle, Oscillate
anim.postInfinityBehavior = Animation.Behavior.Constant
anim.interpolationMode    = Animation.InterpolationMode.Linear  # or Hermite
anim.enableWarping        = True/False
```

---

## RenderSettings

```python
settings = sceneBuilder.renderSettings
settings.useEnvLight          = True   # enable environment lighting
settings.useAnalyticLights    = True   # enable point/directional/area lights
settings.useEmissiveLights    = True   # enable emissive geometry
settings.useGridVolumes       = True   # enable volumetric grids
settings.diffuseAlbedoMultiplier = 1.0 # global albedo scale
```

---

## GridVolume

```python
volume = GridVolume('name')
volume.loadGrid(GridVolume.GridSlot.Density, 'path/to/volume.vdb', 'gridname')
volume.loadGridSequence(GridVolume.GridSlot.Density, ['frame0.vdb', 'frame1.vdb'], 'gridname')
```

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Volume name |
| `densityGrid` | `Grid` | Density grid |
| `densityScale` | `float` | Density scaling factor |
| `emissionGrid` | `Grid` | Emission grid |
| `emissionScale` | `float` | Emission scaling factor |
| `albedo` | `float3` | Volume albedo |
| `anisotropy` | `float` | Phase function anisotropy |
| `emissionMode` | enum | `Direct` or `Blackbody` |
| `emissionTemperature` | `float` | Blackbody temperature |
| `gridFrame` | `uint32` | Current grid frame |
| `gridFrameCount` | `uint32` | Read-only, total frames |
| `frameRate` | `float` | Playback frame rate |
| `playbackEnabled` | `bool` | Enable/disable playback |

**GridSlot** values: `Density`, `Emission`

---

## SceneBuilderFlags

```python
# Pass via importScene options or check via sceneBuilder.flags
SceneBuilderFlags.Default
SceneBuilderFlags.DontMergeMaterials
SceneBuilderFlags.DontMergeMeshes
SceneBuilderFlags.DontOptimizeGraph
SceneBuilderFlags.DontOptimizeMaterials
SceneBuilderFlags.DontUseDisplacement
SceneBuilderFlags.UseOriginalTangentSpace
SceneBuilderFlags.AssumeLinearSpaceTextures
SceneBuilderFlags.UseSpecGlossMaterials
SceneBuilderFlags.UseMetalRoughMaterials
SceneBuilderFlags.UseCompressedHitInfo
SceneBuilderFlags.UseCache
SceneBuilderFlags.RebuildCache
```

---

## Vector Types

Available globally in .pyscene scripts:

- `float2(x, y)`, `float3(x, y, z)`, `float4(x, y, z, w)`
- `int2`, `int3`, `int4`, `uint2`, `uint3`, `uint4`
- `bool2`, `bool3`, `bool4`
- Component access: `.x`, `.y`, `.z`, `.w`
- Arithmetic operators: `+`, `-`, `*`, `/`

---

## Complete Example (Arcade-style)

```python
# 1. Import geometry
sceneBuilder.importScene('Scene.fbx')

# 2. Tweak an existing material
m = sceneBuilder.getMaterial('ScreenMaterial')
m.emissiveFactor = 150.0

# 3. Add environment map
envMap = EnvMap('environment.hdr')
envMap.intensity = 1.0
sceneBuilder.envMap = envMap

# 4. Add camera
camera = Camera('Main')
camera.position = float3(-1.14, 1.84, 2.44)
camera.target   = float3(-0.70, 1.49, 1.62)
camera.up       = float3(0, 1, 0)
camera.focalLength = 21.0
sceneBuilder.addCamera(camera)

# 5. Add lights
sun = DirectionalLight('Sun')
sun.intensity = float3(1.0, 0.77, 0.54)
sun.direction = float3(0.62, -0.72, -0.31)
sceneBuilder.addLight(sun)

fill = PointLight('Fill')
fill.intensity = float3(0.9, 2.4, 3.0)
fill.position  = float3(-2.87, 2.0, 2.99)
sceneBuilder.addLight(fill)

# 6. (Optional) Render settings
settings = sceneBuilder.renderSettings
settings.useEnvLight       = True
settings.useAnalyticLights = True
settings.useEmissiveLights = True
```

---

## Per-Mesh Construction Example (VeachAjar-style)

```python
# Create materials
glass = Material('Glass')
glass.specularTransmission = 1.0
glass.indexOfRefraction = 1.5

metal = Material('Metal')
metal.roughness = 0.17
metal.metallic = 1
metal.baseColor = float4(0.93, 0.92, 0.92, 1)

diffuse = Material('Diffuse')
diffuse.baseColor = float4(0.8, 0.8, 0.8, 1)
diffuse.roughness = 1

# Load individual meshes
obj = TriangleMesh.createFromFile('models/Table.obj')
sceneBuilder.addMeshInstance(
    sceneBuilder.addTriangleMesh(obj, diffuse),
    sceneBuilder.addNode('Table', Transform())
)

# Procedural geometry
quad = TriangleMesh.createQuad(size=float2(2, 2))
xform = Transform()
xform.translation = float3(0, 3, 0)
xform.rotationEulerDeg = float3(90, 0, 0)
sceneBuilder.addMeshInstance(
    sceneBuilder.addTriangleMesh(quad, metal),
    sceneBuilder.addNode('Ceiling', xform)
)
```
