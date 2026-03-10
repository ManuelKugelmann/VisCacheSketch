# 11. Cache-Free Alternatives

Screen-space alternatives capture substantial benefit at lower cost, particularly for DI.

| Approach | μ quality | Helps GI? | Camera-robust? |
|---|---|---|---|
| Vprev | Binary | No | No |
| Poll + EMA | Fractional | No | Partial |
| Hash cache | Converged | Yes | Yes |
