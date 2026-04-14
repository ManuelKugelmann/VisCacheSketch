"""Generate a 1×1 Radiance HDR with a constant sky-blue color."""
import math, os, sys

def float_to_rgbe(r, g, b):
    max_val = max(r, g, b)
    if max_val < 1e-32:
        return bytes(4)
    e = math.floor(math.log2(max_val)) + 1
    scale = math.ldexp(1.0, -e + 8)
    return bytes([min(255, int(r * scale)),
                  min(255, int(g * scale)),
                  min(255, int(b * scale)),
                  e + 128])

# Sky blue (135, 206, 235) linearised, intensity 4
r = ((135 / 255) ** 2.2) * 4
g = ((206 / 255) ** 2.2) * 4
b = ((235 / 255) ** 2.2) * 4

header = b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n"
pixel  = float_to_rgbe(r, g, b)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "runtime", "media", "sky_blue.hdr")
out = os.path.normpath(out)
with open(out, "wb") as f:
    f.write(header)
    f.write(pixel)
print(f"Written {out}  ({r:.3f}, {g:.3f}, {b:.3f})")
