# SiliconRoute Phase 5.3: Independent Verification Report
**Date / Timestamp:** 2026-09-28 22:37:42 UTC
**Verifier Role:** Independent Verifier (Strictly READ-ONLY)
**Target Commits:** `bbbf098` and `25fdfe4`
**Database:** `data/siliconroute.db`
**SHA256 (Pre-Verification):**  `bea0ec3572e02914d05352a9370d6044841d25223639e2be669b00335728ab98`
**SHA256 (Post-Verification):** `bea0ec3572e02914d05352a9370d6044841d25223639e2be669b00335728ab98`
**Immutability Integrity:** CONFIRMED (Bit-for-bit identical, zero writes executed)

---
## 1. Verification of `results/claims_phase5_3.json` (25 Claims) & 5 Extra Queries

All 25 claims were executed verbatim in subshell using the exact command specified in `how`.

| ID | Claim | Expected Value | Measured Value | Status |
|:---|:---|:---:|:---:|:---:|
| `claim_01` | Total workload measurements stored in database | `72` | `72` | PASS |
| `claim_02` | Total decisions in Phase 5.3 hardware evaluation run (IDs 93 to 116) | `24` | `24` | PASS |
| `claim_03` | SiliconRoute winning decisions out of 24 in Phase 5.3 evaluation | `22` | `22` | PASS |
| `claim_04` | SiliconRoute accuracy percentage in Phase 5.3 evaluation | `91.7` | `91.7` | PASS |
| `claim_05` | SiliconRoute mean regret percentage in Phase 5.3 evaluation | `2.03` | `2.03` | PASS |
| `claim_06` | SiliconRoute p90 regret percentage in Phase 5.3 evaluation | `0.0` | `0.0` | PASS |
| `claim_07` | Always-CPU winning decisions out of 24 in Phase 5.3 evaluation | `13` | `13` | PASS |
| `claim_08` | Always-CPU accuracy percentage in Phase 5.3 evaluation | `54.2` | `54.2` | PASS |
| `claim_09` | Always-CPU mean regret percentage in Phase 5.3 evaluation | `92.77` | `92.77` | PASS |
| `claim_10` | Always-RTX winning decisions out of 24 in Phase 5.3 evaluation | `11` | `11` | PASS |
| `claim_11` | Always-RTX accuracy percentage in Phase 5.3 evaluation | `45.8` | `45.8` | PASS |
| `claim_12` | Always-RTX mean regret percentage in Phase 5.3 evaluation | `297.3` | `297.3` | PASS |
| `claim_13` | Fit-Only router winning decisions out of 24 in Phase 5.3 evaluation | `21` | `21` | PASS |
| `claim_14` | Fit-Only router accuracy percentage in Phase 5.3 evaluation | `87.5` | `87.5` | PASS |
| `claim_15` | Fit-Only router mean regret percentage in Phase 5.3 evaluation | `26.16` | `26.16` | PASS |
| `claim_16` | SiliconRoute accuracy percentage in idle_loaded workload | `100.0` | `100.0` | PASS |
| `claim_17` | SiliconRoute mean regret percentage in idle_loaded workload | `0.0` | `0.0` | PASS |
| `claim_18` | SiliconRoute accuracy percentage in cold_start workload | `87.5` | `87.5` | PASS |
| `claim_19` | SiliconRoute mean regret percentage in cold_start workload | `0.85` | `0.85` | PASS |
| `claim_20` | SiliconRoute accuracy percentage in sustained workload | `87.5` | `87.5` | PASS |
| `claim_21` | SiliconRoute mean regret percentage in sustained workload | `5.22` | `5.22` | PASS |
| `claim_22` | Total historical runs stored in database (0 runs deleted) | `456` | `456` | PASS |
| `claim_23` | Historical runs flagged as identity_suspect | `12` | `12` | PASS |
| `claim_24` | Physical DXGI VendorId for NVIDIA GeForce RTX 5070 Laptop GPU (dml:1) | `0x10DE` | `0x10DE` | PASS |
| `claim_25` | Physical DXGI VendorId for AMD Radeon 610M (dml:0) | `0x1002` | `0x1002` | PASS |

### Extra Independent Metrics from Builder's Report (Not in Claims File)

| Metric Description | Expected in Report | Independent SQL / Recomputation | Status |
|:---|:---:|:---:|:---:|
| Decision 100 measured regret percentage | `6.8%` | `6.8%` | PASS |
| Decision 105 measured regret percentage | `41.8%` | `41.8%` | PASS |
| Always-RTX accuracy in sustained workload (4/8) | `50.0%` | `50.0% (4/8)` | PASS |
| Always-CPU accuracy in cold_start workload (6/8) | `75.0%` | `75.0% (6/8)` | PASS |
| Fit-Only router accuracy in sustained workload (8/8) | `100.0%` | `100.0% (8/8)` | PASS |

---
## 2. Independent Recomputation: Database Counts, Sessions & Workload Metrics

- **Total Rows in `run` Table:** `456` (Expected: `456`, Matches: `True`)
- **Runs with `session_id IS NULL`:** `0` (Expected: `0`, Matches: `True`)
- **Sum of Runs Grouped by Session:** `456` (Exact match with `COUNT(*)`: `True`)

### Runs Per Session and Device

| Session ID | Description / Kind | Device ID | Device Key | Run Count |
|:---|:---|:---:|:---:|:---:|
| 9 | Phase 2 Real Latency Benchmark | 1 | `cpu` | 4 |
| 9 | Phase 2 Real Latency Benchmark | 2 | `dml:0` | 4 |
| 9 | Phase 2 Real Latency Benchmark | 3 | `dml:1` | 4 |
| 9 | Phase 2 Real Latency Benchmark | 4 | `dml:2` | 4 |
| 17 | Phase 2.5 Robust Timing + Device Ident... | 1 | `cpu` | 4 |
| 17 | Phase 2.5 Robust Timing + Device Ident... | 2 | `dml:0` | 4 |
| 17 | Phase 2.5 Robust Timing + Device Ident... | 3 | `dml:1` | 4 |
| 17 | Phase 2.5 Robust Timing + Device Ident... | 4 | `dml:2` | 4 |
| 18 | Phase 2.5 Robust Timing Verification | 1 | `cpu` | 4 |
| 18 | Phase 2.5 Robust Timing Verification | 2 | `dml:0` | 4 |
| 18 | Phase 2.5 Robust Timing Verification | 3 | `dml:1` | 4 |
| 32 | Phase 3 Gate - Benchmark Session A | 1 | `cpu` | 4 |
| 32 | Phase 3 Gate - Benchmark Session A | 2 | `dml:0` | 4 |
| 32 | Phase 3 Gate - Benchmark Session A | 3 | `dml:1` | 4 |
| 33 | Phase 3 Gate - Benchmark Session B | 1 | `cpu` | 4 |
| 33 | Phase 3 Gate - Benchmark Session B | 2 | `dml:0` | 4 |
| 33 | Phase 3 Gate - Benchmark Session B | 3 | `dml:1` | 4 |
| 38 | Phase 3 Proof: Real NVML energy measur... | 3 | `dml:1` | 1 |
| 84 | Phase 4 full ladder benchmark for hard... | 1 | `cpu` | 45 |
| 84 | Phase 4 full ladder benchmark for hard... | 2 | `dml:0` | 45 |
| 84 | Phase 4 full ladder benchmark for hard... | 3 | `dml:1` | 45 |
| 85 | Phase 4.1: Extended synthetic ladders ... | 1 | `cpu` | 12 |
| 85 | Phase 4.1: Extended synthetic ladders ... | 2 | `dml:0` | 12 |
| 85 | Phase 4.1: Extended synthetic ladders ... | 3 | `dml:1` | 12 |
| 86 | Live API re-run: mlp-3072w-4l batch 1 ... | 1 | `cpu` | 1 |
| 86 | Live API re-run: mlp-3072w-4l batch 1 ... | 3 | `dml:1` | 1 |
| 87 | Phase 4.2 Batch Anomaly Investigation:... | 2 | `dml:0` | 12 |
| 87 | Phase 4.2 Batch Anomaly Investigation:... | 3 | `dml:1` | 12 |
| 88 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 88 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 88 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 89 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 89 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 89 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 90 | Router verification: mlp-256w-4l (B=32... | 1 | `cpu` | 1 |
| 90 | Router verification: mlp-256w-4l (B=32... | 2 | `dml:0` | 1 |
| 90 | Router verification: mlp-256w-4l (B=32... | 3 | `dml:1` | 1 |
| 91 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 91 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 92 | Router verification: mlp-1024w-4l (B=8... | 1 | `cpu` | 1 |
| 92 | Router verification: mlp-1024w-4l (B=8... | 3 | `dml:1` | 1 |
| 93 | Router verification: mlp-1024w-4l (B=3... | 1 | `cpu` | 1 |
| 93 | Router verification: mlp-1024w-4l (B=3... | 3 | `dml:1` | 1 |
| 94 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 95 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 96 | Router verification: mlp-3072w-4l (B=3... | 1 | `cpu` | 1 |
| 97 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 98 | Router verification: conv-16c-4l (B=8)... | 1 | `cpu` | 1 |
| 99 | Router verification: conv-16c-4l (B=32... | 1 | `cpu` | 1 |
| 100 | Router verification: conv-64c-4l (B=1)... | 1 | `cpu` | 1 |
| 101 | Router verification: conv-64c-4l (B=8)... | 1 | `cpu` | 1 |
| 102 | Router verification: conv-64c-4l (B=32... | 1 | `cpu` | 1 |
| 103 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 104 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 105 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 105 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 105 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 106 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 106 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 107 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 108 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 108 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 108 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 109 | Router verification: mlp-3072w-4l (B=3... | 1 | `cpu` | 1 |
| 110 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 110 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 111 | Router verification: conv-16c-4l (B=8)... | 1 | `cpu` | 1 |
| 112 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 112 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 112 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 113 | Router verification: conv-96c-4l (B=32... | 1 | `cpu` | 1 |
| 114 | Router verification: mlp-256w-4l (B=32... | 1 | `cpu` | 1 |
| 114 | Router verification: mlp-256w-4l (B=32... | 2 | `dml:0` | 1 |
| 114 | Router verification: mlp-256w-4l (B=32... | 3 | `dml:1` | 1 |
| 115 | Router verification: conv-96c-4l (B=32... | 1 | `cpu` | 1 |
| 116 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 116 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 116 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 117 | Router verification: mlp-256w-4l (B=32... | 1 | `cpu` | 1 |
| 117 | Router verification: mlp-256w-4l (B=32... | 2 | `dml:0` | 1 |
| 117 | Router verification: mlp-256w-4l (B=32... | 3 | `dml:1` | 1 |
| 118 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 119 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 119 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 119 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 120 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 121 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 122 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 123 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 124 | Router verification: conv-16c-4l (B=8)... | 1 | `cpu` | 1 |
| 125 | Router verification: mlp-3072w-4l (B=3... | 1 | `cpu` | 1 |
| 126 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 126 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 127 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 128 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 129 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 130 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 131 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 132 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 132 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 132 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 133 | Router verification: mlp-3072w-4l (B=3... | 1 | `cpu` | 1 |
| 133 | Router verification: mlp-3072w-4l (B=3... | 2 | `dml:0` | 1 |
| 133 | Router verification: mlp-3072w-4l (B=3... | 3 | `dml:1` | 1 |
| 134 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 134 | Router verification: mlp-1024w-4l (B=1... | 2 | `dml:0` | 1 |
| 134 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 135 | Router verification: conv-16c-4l (B=8)... | 1 | `cpu` | 1 |
| 135 | Router verification: conv-16c-4l (B=8)... | 2 | `dml:0` | 1 |
| 135 | Router verification: conv-16c-4l (B=8)... | 3 | `dml:1` | 1 |
| 136 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 136 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 136 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 137 | Router verification: conv-96c-4l (B=32... | 1 | `cpu` | 1 |
| 137 | Router verification: conv-96c-4l (B=32... | 2 | `dml:0` | 1 |
| 137 | Router verification: conv-96c-4l (B=32... | 3 | `dml:1` | 1 |
| 138 | Router verification: mlp-256w-4l (B=32... | 1 | `cpu` | 1 |
| 138 | Router verification: mlp-256w-4l (B=32... | 2 | `dml:0` | 1 |
| 138 | Router verification: mlp-256w-4l (B=32... | 3 | `dml:1` | 1 |
| 139 | Router verification: conv-96c-4l (B=32... | 1 | `cpu` | 1 |
| 139 | Router verification: conv-96c-4l (B=32... | 2 | `dml:0` | 1 |
| 139 | Router verification: conv-96c-4l (B=32... | 3 | `dml:1` | 1 |
| 140 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 140 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 140 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 141 | Router verification: mlp-256w-4l (B=32... | 1 | `cpu` | 1 |
| 141 | Router verification: mlp-256w-4l (B=32... | 2 | `dml:0` | 1 |
| 141 | Router verification: mlp-256w-4l (B=32... | 3 | `dml:1` | 1 |
| 142 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 142 | Router verification: mlp-3072w-4l (B=1... | 2 | `dml:0` | 1 |
| 142 | Router verification: mlp-3072w-4l (B=1... | 3 | `dml:1` | 1 |
| 143 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 143 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 143 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 144 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 144 | Router verification: conv-16c-4l (B=1)... | 2 | `dml:0` | 1 |
| 144 | Router verification: conv-16c-4l (B=1)... | 3 | `dml:1` | 1 |
| 145 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 145 | Router verification: conv-96c-4l (B=1)... | 2 | `dml:0` | 1 |
| 145 | Router verification: conv-96c-4l (B=1)... | 3 | `dml:1` | 1 |
| 146 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 146 | Router verification: conv-96c-4l (B=8)... | 2 | `dml:0` | 1 |
| 146 | Router verification: conv-96c-4l (B=8)... | 3 | `dml:1` | 1 |
| 147 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 147 | Router verification: mlp-3072w-4l (B=8... | 2 | `dml:0` | 1 |
| 147 | Router verification: mlp-3072w-4l (B=8... | 3 | `dml:1` | 1 |
| 148 | Router verification: conv-16c-4l (B=8)... | 1 | `cpu` | 1 |
| 148 | Router verification: conv-16c-4l (B=8)... | 2 | `dml:0` | 1 |
| 148 | Router verification: conv-16c-4l (B=8)... | 3 | `dml:1` | 1 |
| 149 | Router verification: mlp-3072w-4l (B=3... | 1 | `cpu` | 1 |
| 149 | Router verification: mlp-3072w-4l (B=3... | 2 | `dml:0` | 1 |
| 149 | Router verification: mlp-3072w-4l (B=3... | 3 | `dml:1` | 1 |
| 150 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 150 | Router verification: mlp-1024w-4l (B=1... | 2 | `dml:0` | 1 |
| 150 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 151 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 151 | Router verification: conv-96c-4l (B=1)... | 2 | `dml:0` | 1 |
| 151 | Router verification: conv-96c-4l (B=1)... | 3 | `dml:1` | 1 |
| 152 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 152 | Router verification: conv-96c-4l (B=8)... | 2 | `dml:0` | 1 |
| 152 | Router verification: conv-96c-4l (B=8)... | 3 | `dml:1` | 1 |
| 153 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 153 | Router verification: mlp-3072w-4l (B=1... | 2 | `dml:0` | 1 |
| 153 | Router verification: mlp-3072w-4l (B=1... | 3 | `dml:1` | 1 |
| 154 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 154 | Router verification: mlp-3072w-4l (B=8... | 2 | `dml:0` | 1 |
| 154 | Router verification: mlp-3072w-4l (B=8... | 3 | `dml:1` | 1 |
| 155 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 155 | Router verification: conv-16c-4l (B=1)... | 2 | `dml:0` | 1 |
| 155 | Router verification: conv-16c-4l (B=1)... | 3 | `dml:1` | 1 |
| 156 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 156 | Router verification: conv-16c-4l (B=1)... | 2 | `dml:0` | 1 |
| 156 | Router verification: conv-16c-4l (B=1)... | 3 | `dml:1` | 1 |
| 158 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 158 | Router verification: conv-96c-4l (B=1)... | 2 | `dml:0` | 1 |
| 158 | Router verification: conv-96c-4l (B=1)... | 3 | `dml:1` | 1 |
| 167 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 167 | Router verification: mlp-3072w-4l (B=8... | 2 | `dml:0` | 1 |
| 167 | Router verification: mlp-3072w-4l (B=8... | 3 | `dml:1` | 1 |
| 168 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 168 | Router verification: conv-96c-4l (B=8)... | 2 | `dml:0` | 1 |
| 168 | Router verification: conv-96c-4l (B=8)... | 3 | `dml:1` | 1 |
| 169 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 169 | Router verification: mlp-1024w-4l (B=1... | 2 | `dml:0` | 1 |
| 169 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 170 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 170 | Router verification: mlp-3072w-4l (B=1... | 2 | `dml:0` | 1 |
| 170 | Router verification: mlp-3072w-4l (B=1... | 3 | `dml:1` | 1 |
| 177 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 177 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 177 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 178 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 178 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 178 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |
| 180 | Router verification: conv-16c-4l (B=1)... | 1 | `cpu` | 1 |
| 180 | Router verification: conv-16c-4l (B=1)... | 2 | `dml:0` | 1 |
| 180 | Router verification: conv-16c-4l (B=1)... | 3 | `dml:1` | 1 |
| 182 | Router verification: conv-96c-4l (B=1)... | 1 | `cpu` | 1 |
| 182 | Router verification: conv-96c-4l (B=1)... | 2 | `dml:0` | 1 |
| 182 | Router verification: conv-96c-4l (B=1)... | 3 | `dml:1` | 1 |
| 191 | Router verification: mlp-3072w-4l (B=8... | 1 | `cpu` | 1 |
| 191 | Router verification: mlp-3072w-4l (B=8... | 2 | `dml:0` | 1 |
| 191 | Router verification: mlp-3072w-4l (B=8... | 3 | `dml:1` | 1 |
| 192 | Router verification: conv-96c-4l (B=8)... | 1 | `cpu` | 1 |
| 192 | Router verification: conv-96c-4l (B=8)... | 2 | `dml:0` | 1 |
| 192 | Router verification: conv-96c-4l (B=8)... | 3 | `dml:1` | 1 |
| 193 | Router verification: mlp-1024w-4l (B=1... | 1 | `cpu` | 1 |
| 193 | Router verification: mlp-1024w-4l (B=1... | 2 | `dml:0` | 1 |
| 193 | Router verification: mlp-1024w-4l (B=1... | 3 | `dml:1` | 1 |
| 194 | Router verification: mlp-3072w-4l (B=1... | 1 | `cpu` | 1 |
| 194 | Router verification: mlp-3072w-4l (B=1... | 2 | `dml:0` | 1 |
| 194 | Router verification: mlp-3072w-4l (B=1... | 3 | `dml:1` | 1 |
| 201 | Router verification: mlp-256w-4l (B=1)... | 1 | `cpu` | 1 |
| 201 | Router verification: mlp-256w-4l (B=1)... | 2 | `dml:0` | 1 |
| 201 | Router verification: mlp-256w-4l (B=1)... | 3 | `dml:1` | 1 |
| 202 | Router verification: mlp-256w-4l (B=8)... | 1 | `cpu` | 1 |
| 202 | Router verification: mlp-256w-4l (B=8)... | 2 | `dml:0` | 1 |
| 202 | Router verification: mlp-256w-4l (B=8)... | 3 | `dml:1` | 1 |

### Routing Accuracy and Regret Recomputation (Decisions 93 to 116)

| Workload | Policy | Wins (k/n) | Accuracy | Mean Regret | P90 Regret |
|:---|:---|:---:|:---:|:---:|:---:|
| `sustained` | **SiliconRoute** | 7/8 | 87.5% | 5.22% | 12.54% |
| `sustained` | **Always-CPU** | 4/8 | 50.0% | 142.63% | 380.89% |
| `sustained` | **Always-RTX** | 4/8 | 50.0% | 144.21% | 433.06% |
| `sustained` | **Fit-Only Router** | 8/8 | 100.0% | 0.0% | 0.0% |
| `idle_loaded` | **SiliconRoute** | 8/8 | 100.0% | 0.0% | 0.0% |
| `idle_loaded` | **Always-CPU** | 3/8 | 37.5% | 134.19% | 369.38% |
| `idle_loaded` | **Always-RTX** | 5/8 | 62.5% | 152.27% | 547.29% |
| `idle_loaded` | **Fit-Only Router** | 7/8 | 87.5% | 1.54% | 3.7% |
| `cold_start` | **SiliconRoute** | 7/8 | 87.5% | 0.85% | 2.05% |
| `cold_start` | **Always-CPU** | 6/8 | 75.0% | 1.49% | 4.7% |
| `cold_start` | **Always-RTX** | 2/8 | 25.0% | 595.42% | 1342.22% |
| `cold_start` | **Fit-Only Router** | 6/8 | 75.0% | 76.94% | 229.99% |
| `overall` | **SiliconRoute** | 22/24 | 91.7% | 2.03% | 0.0% |
| `overall` | **Always-CPU** | 13/24 | 54.2% | 92.77% | 337.55% |
| `overall` | **Always-RTX** | 11/24 | 45.8% | 297.3% | 971.8% |
| `overall` | **Fit-Only Router** | 21/24 | 87.5% | 26.16% | 8.63% |

---
## 3. Hardware Identity & GPU Swap Audit

- **Total Flagged `identity_suspect = 1` Runs:** `12` (Expected: `12`)

### Evidence for Every `identity_suspect = 1` Run

| Run ID | Session | Device | Model | Batch | Measured Time | Swap Evidence |
|:---|:---:|:---:|:---|:---:|:---:|:---|
| 774 | 156 | `dml:0` | `conv-16c-4l` | 1 | `0.240 ms` | Ran at RTX speed: 0.240 ms (vs Normal RTX 0.254 ms, Normal Radeon 0.471 ms) |
| 775 | 156 | `dml:1` | `conv-16c-4l` | 1 | `0.471 ms` | Ran at Radeon speed: 0.471 ms (vs Normal RTX 0.254 ms, Normal Radeon 0.471 ms) |
| 777 | 158 | `dml:0` | `conv-96c-4l` | 1 | `0.684 ms` | Ran at RTX speed: 0.684 ms (vs Normal RTX 0.702 ms, Normal Radeon 3.607 ms) |
| 778 | 158 | `dml:1` | `conv-96c-4l` | 1 | `3.463 ms` | Ran at Radeon speed: 3.463 ms (vs Normal RTX 0.702 ms, Normal Radeon 3.607 ms) |
| 780 | 167 | `dml:0` | `mlp-3072w-4l` | 8 | `1.062 ms` | Ran at RTX speed: 1.062 ms (vs Normal RTX 1.017 ms, Normal Radeon 24.684 ms) |
| 781 | 167 | `dml:1` | `mlp-3072w-4l` | 8 | `18.958 ms` | Ran at Radeon speed: 18.958 ms (vs Normal RTX 1.017 ms, Normal Radeon 24.684 ms) |
| 783 | 168 | `dml:0` | `conv-96c-4l` | 8 | `8.695 ms` | Ran at RTX speed: 8.695 ms (vs Normal RTX 18.683 ms, Normal Radeon 39.912 ms) |
| 784 | 168 | `dml:1` | `conv-96c-4l` | 8 | `35.018 ms` | Ran at Radeon speed: 35.018 ms (vs Normal RTX 18.683 ms, Normal Radeon 39.912 ms) |
| 786 | 169 | `dml:0` | `mlp-1024w-4l` | 1 | `0.165 ms` | Ran at RTX speed: 0.165 ms (vs Normal RTX 0.182 ms, Normal Radeon 0.641 ms) |
| 787 | 169 | `dml:1` | `mlp-1024w-4l` | 1 | `0.595 ms` | Ran at Radeon speed: 0.595 ms (vs Normal RTX 0.182 ms, Normal Radeon 0.641 ms) |
| 789 | 170 | `dml:0` | `mlp-3072w-4l` | 1 | `0.665 ms` | Ran at RTX speed: 0.665 ms (vs Normal RTX 0.618 ms, Normal Radeon 6.318 ms) |
| 790 | 170 | `dml:1` | `mlp-3072w-4l` | 1 | `4.376 ms` | Ran at Radeon speed: 4.376 ms (vs Normal RTX 0.618 ms, Normal Radeon 6.318 ms) |

### Swap Detector on Unflagged GPU Runs (>2x Differentiated Configurations)
- **Configurations Evaluated (>2x Baseline Median Spread):** `182` GPU runs
- **Unflagged Runs Matching Swap Condition:** `0`
- **Result:** Exactly `0` unflagged GPU runs match swap behavior. All genuine runs match their physical hardware characteristics.

---
## 4. Physics Sanity Audit & Datasheet Limits

### Hardware Theoretical Ceilings (*Datasheet, not measured*)
- **CPU (AMD Ryzen 9 8940HX):** FP32 ~1,400 GFLOP/s (*datasheet, not measured*), DRAM ~83.2 GB/s (*datasheet, not measured*)
- **iGPU (AMD Radeon 610M, `dml:0`):** FP32 ~563 GFLOP/s (*datasheet, not measured*), DRAM ~83.2 GB/s (*datasheet, not measured*)
- **dGPU (NVIDIA RTX 5070 Laptop, `dml:1`):** FP32 ~25,000 GFLOP/s (*datasheet, not measured*), VRAM ~320 GB/s (*datasheet, not measured*)

- **Unflagged MLP Runs Exceeding Datasheet Compute Peak:** `0` (Must be `0`)
- **Conv Runs with Implied Compute > Peak (Winograd Hypothesis):** `19`

### Convolution Runs Exceeding Datasheet Peak (Physics Notes)

| Run ID | Session | Device | Model | Batch | Implied Compute | Datasheet Peak | Suspect Flag | Physics Note |
|:---|:---:|:---:|:---|:---:|:---:|:---:|:---:|:---|
| 560 | 84 | `dml:0` | `conv-64c-4l` | 1 | `701.9 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 701.9 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 561 | 84 | `dml:0` | `conv-64c-4l` | 8 | `642.4 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 642.4 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 562 | 84 | `dml:0` | `conv-64c-4l` | 32 | `627.9 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 627.9 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 585 | 85 | `dml:0` | `conv-96c-4l` | 1 | `766.7 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 766.7 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 594 | 85 | `dml:0` | `conv-128c-4l` | 1 | `792.9 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 792.9 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 597 | 85 | `dml:0` | `conv-128c-4l` | 8 | `593.0 GFLOP/s` | `563 GFLOP/s` | `0` | Algorithmic Winograd complexity reduction |
| 600 | 85 | `dml:0` | `conv-128c-4l` | 32 | `590.3 GFLOP/s` | `563 GFLOP/s` | `0` | Algorithmic Winograd complexity reduction |
| 625 | 87 | `dml:0` | `conv-96c-4l` | 1 | `765.2 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 765.2 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 626 | 87 | `dml:0` | `conv-96c-4l` | 2 | `755.8 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 755.8 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 627 | 87 | `dml:0` | `conv-96c-4l` | 4 | `729.9 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 729.9 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 628 | 87 | `dml:0` | `conv-96c-4l` | 8 | `597.5 GFLOP/s` | `563 GFLOP/s` | `0` | Algorithmic Winograd complexity reduction |
| 629 | 87 | `dml:0` | `conv-96c-4l` | 16 | `577.3 GFLOP/s` | `563 GFLOP/s` | `0` | Algorithmic Winograd complexity reduction |
| 630 | 87 | `dml:0` | `conv-96c-4l` | 32 | `611.4 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 611.4 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 718 | 137 | `dml:0` | `conv-96c-4l` | 32 | `686.9 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 686.9 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 742 | 145 | `dml:0` | `conv-96c-4l` | 1 | `733.0 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 733.0 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 760 | 151 | `dml:0` | `conv-96c-4l` | 1 | `765.4 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 765.4 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 777 | 158 | `dml:0` | `conv-96c-4l` | 1 | `3973.6 GFLOP/s` | `563 GFLOP/s` | `1` | Winograd hypothesis: implied 3973.6 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 783 | 168 | `dml:0` | `conv-96c-4l` | 8 | `2500.7 GFLOP/s` | `563 GFLOP/s` | `1` | Winograd hypothesis: implied 2500.7 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |
| 801 | 182 | `dml:0` | `conv-96c-4l` | 1 | `738.4 GFLOP/s` | `563 GFLOP/s` | `0` | Winograd hypothesis: implied 738.4 GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) due to reduced multiplication complexity in convolution |

> **Physics Evaluation:** In direct GEMM, 3x3 2D convolution requires $2 \times C_{in} \times C_{out} \times K_h \times K_w \times H \times W$ operations. Under Winograd minimal filtering algorithms ($F(2\times 2, 3\times 3)$ or $F(4\times 4, 3\times 3)$), multiplication complexity is reduced by $2.25\times$ to $4.0\times$. The implied GFLOP/s exceeds theoretical GEMM compute because DirectML executes Winograd transformations on small tiles rather than brute-force matrix multiplication. Exactly 0 unflagged MLP runs exceed theoretical limits.

---
## 5. Process Integrity & Codebase Audit

- **Automated Test Suite:** `47 passed, 1 warning in 32.71s` (PASS)
- **Git Reflog Audit:** CLEAN (No amend/reset detected since df996e1)
- **Runs with `session_id IS NULL`:** `0` (PASS)
- **Tracked Database Files (`git ls-files *.db`):** `0` files (PASS)
- **Hardcoded Mock Values in `app/`:** `0` findings (PASS)
- **Database Bit-for-Bit Hash Immutability:** `bea0ec3572e02914d05352a9370d6044841d25223639e2be669b00335728ab98` == `bea0ec3572e02914d05352a9370d6044841d25223639e2be669b00335728ab98` (PASS)

---
## 6. Verification Summary & Final Verdict

| Audit Dimension | Verification Standard | Result | Status |
|:---|:---|:---:|:---:|
| Claims Verification (25 Claims) | Verified independently via script & SQL | `PASS` | **PASS** |
| Extra Unclaimed Metrics (5 Queries) | Verified independently via script & SQL | `PASS` | **PASS** |
| Total Database Runs (Expect 456) | Verified independently via script & SQL | `PASS` | **PASS** |
| Independent Metric Recomputation (22/24 Wins, 91.7%) | Verified independently via script & SQL | `PASS` | **PASS** |
| Hardware Identity (0 Unflagged Swaps across >2x Differentiated Runs) | Verified independently via script & SQL | `PASS` | **PASS** |
| Physics Sanity (0 Unflagged MLP Runs > Datasheet Peak) | Verified independently via script & SQL | `PASS` | **PASS** |
| Process Integrity (pytest green, clean reflog, 0 NULL sessions, 0 mocks) | Verified independently via script & SQL | `PASS` | **PASS** |
| Database Immutability (Bit-for-Bit SHA256 Match Pre/Post) | Verified independently via script & SQL | `PASS` | **PASS** |

## VERDICT: PASS