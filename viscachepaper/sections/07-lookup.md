# 7. Lookup

**Algorithm 2: Coarse-to-Fine Lookup**
```
Input: pos_a, pos_b, camera_pos
best <- MISS
di <- distance_lod_interval(pos_a, camera_pos)
for l <- di.min_level to di.max_level do
  slot <- find(fp(pos_a,pos_b,l), hash(pos_a,pos_b,l))
  if slot < 0 then break              // no entry
  e <- table[slot]
  if e.total < w_min then break        // too sparse
  p <- e.vis / e.total
  best <- (mean=p, var=p(1-p), level=l)
  if best.var < tau then break         // clean enough
return best
```

Four stopping conditions: distance interval bounds, no entry, too few samples, low variance.
