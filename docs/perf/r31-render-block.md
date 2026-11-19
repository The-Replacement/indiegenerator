# RENDER_BLOCK measurement (issue #31)

## Method

One method for all sizes: stdlib resource.getrusage (RUSAGE_SELF.ru_maxrss, with RUSAGE_CHILDREN.ru_maxrss as a fresh-process cross-check) + time.perf_counter. One fresh OS process per cell, because ru_maxrss is a high-water mark. peak_mb = ru_maxrss_kib / 1024 (Linux KiB). The worker sets indiegen.render.RENDER_BLOCK = N before calling indiegen.cli._render(preset, seed, None, seconds, out_dir, None, None) with the c29 values (ambient/1042/900 and motorik/1042/480). /usr/bin/time is not installed and is not substituted. Historical README columns measured with a different tool are never used as data.

One fresh OS process per cell; baseline first (131072, 32768, 16384).

## Measured cells

| size | ambient 900 wall_s | ambient 900 peak_mb | motorik 480 wall_s | motorik 480 peak_mb | survives |
|---:|---:|---:|---:|---:|:---|
| 131072 | 275.006 | 1361.7 | 99.154 | 690.3 | no |
| 32768 | 259.719 | 1314.0 | 97.673 | 691.4 | no |
| 16384 | 270.607 | 1308.6 | 101.577 | 693.0 | no |

## Decision

- choice: A
- adopted size: None
- survivors: []
- breaches: []
- note: No candidate both stays inside the 171 s / 1425 MB headroom and improves the baseline by >=5%.
