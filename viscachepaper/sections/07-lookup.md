# 7. Lookup

**Algorithm 2: Coarse-to-Fine Lookup**
```
Input: pos_a, pos_b
best <- MISS
for l <- 0 to N-1 do
  (qa, qb) <- quantize_pair(pos_a, pos_b, cell_size(l), l)
  slot <- find(fp(qa,qb,l), hash(qa,qb,l))
  if slot < 0 then break              // no entry
  e <- table[slot]
  if e.total < w_min then break        // too sparse
  p <- e.vis / e.total
  best <- (mean=p, var=p(1-p), level=l)
  if best.var < tau then break         // clean enough
return best
```

Three stopping conditions: no entry, too few samples, low variance. The cascade always starts at L0 (coarsest) and descends to finer levels until one of these conditions is met.
