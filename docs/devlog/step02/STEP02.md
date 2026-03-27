# Step 02 — Quantization Refinement

Per-variant tuned bin sizes. norm1 family across 4 scenes; norm variants 1 scene only in this run.
Config: 1 warmup + 1 render frame, x1 and x16 SPP, 512×512.

[← Dev Log overview](../DEVLOG.md)

## Overview plot

![](overview_rays_02.png)

## Results summary

| variant | x1 rays % | x1 savings | x1 cold | x16 rays % | x16 savings | x16 cold |
|---------|----------:|-----------:|--------:|-----------:|------------:|---------:|
| pos_norm1__pos1       | 39.7 % | 60.3 % |  0.2 % | 42.0 % | 58.0 % | 0.1 % |
| pos_norm1__dir1_dist1 | 22.3 % | 77.7 % |  0.2 % | 42.0 % | 58.0 % | 0.1 % |
| pos_norm1__pos        | 39.9 % | 60.1 % |  6.2 % | 21.6 % | 78.4 % | 0.1 % |
| pos_norm1__dir_dist1  | 35.7 % | 64.3 % |  3.3 % | 24.2 % | 75.8 % | 0.2 % |
| pos_norm1__dir_dist   | 38.4 % | 61.6 % |  5.5 % | 23.3 % | 76.7 % | 0.3 % |
| pos_norm__dir_dist1 ¹ | 35.6 % | 64.4 % |  4.1 % | **21.0 %** | **79.0 %** | 0.3 % |

¹ 1 scene only.

Tuned quantization + warmup (x16) brings most variants to 21–24% rays traced (~76–79% savings).
__pos1 and __dir1_dist1 show less benefit from x16 warmup — they plateau quickly regardless of cell size.
__pos benefits most from warmup: cold miss drops from 6% to 0.1%.

## Plates — x1 vs x16 SPP

### pos_norm__dir_dist1

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm__dir_dist1_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm__dir_dist1_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>

### pos_norm1__pos1

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm1__pos1_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm1__pos1_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>

### pos_norm1__dir1_dist1

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm1__dir1_dist1_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm1__dir1_dist1_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>

### pos_norm1__pos

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm1__pos_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm1__pos_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>

### pos_norm1__dir_dist1

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm1__dir_dist1_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm1__dir_dist1_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>

### pos_norm1__dir_dist

<table><tr>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm1__dir_dist_plate.png"></td>
<td><img src="plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm1__dir_dist_plate.png"></td>
</tr><tr>
<td align="center">x1 SPP</td>
<td align="center">x16 SPP</td>
</tr></table>
