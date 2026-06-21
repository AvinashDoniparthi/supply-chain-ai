# Benchmark Report

Deterministic regression run using curated supplier evidence and the production validation, classification, verification, confidence, criticality, health, and executive-report stages.

## Summary

| Company | Precision | Recall | Coverage | Tier-1 Suppliers | False Positives | Health |
|---|---:|---:|---|---:|---:|---|
| Apple | 1.000 | 1.000 | High | 7 | 0 | Good (77.3/100) |
| Tesla | 1.000 | 1.000 | High | 4 | 0 | Good (80.0/100) |
| NVIDIA | 1.000 | 1.000 | High | 3 | 0 | Good (78.3/100) |
| Intel | 1.000 | 1.000 | High | 5 | 0 | Good (76.3/100) |
| Samsung | 1.000 | 1.000 | High | 5 | 0 | Good (78.7/100) |

## Company Detail

### Apple

- Precision: 1.000
- Recall: 1.000
- Coverage: High (7/7)
- Health: Good (77.3/100)
- Tier-1 suppliers identified: Broadcom, Corning, Hon Hai Precision Industry, Murata Manufacturing, Pegatron, Samsung Electronics, Taiwan Semiconductor Manufacturing Company
- False positives: None
- False negatives: None
- Malformed entities surviving: None

### Tesla

- Precision: 1.000
- Recall: 1.000
- Coverage: High (4/4)
- Health: Good (80.0/100)
- Tier-1 suppliers identified: Contemporary Amperex Technology Co. Limited, LG Energy Solution, Panasonic, Samsung SDI
- False positives: None
- False negatives: None
- Malformed entities surviving: None

### NVIDIA

- Precision: 1.000
- Recall: 1.000
- Coverage: High (3/3)
- Health: Good (78.3/100)
- Tier-1 suppliers identified: SK Hynix, Samsung Electronics, Taiwan Semiconductor Manufacturing Company
- False positives: None
- False negatives: None
- Malformed entities surviving: None

### Intel

- Precision: 1.000
- Recall: 1.000
- Coverage: High (5/5)
- Health: Good (76.3/100)
- Tier-1 suppliers identified: ASML, Applied Materials, KLA, Lam Research, Tokyo Electron
- False positives: None
- False negatives: None
- Malformed entities surviving: None

### Samsung

- Precision: 1.000
- Recall: 1.000
- Coverage: High (5/5)
- Health: Good (78.7/100)
- Tier-1 suppliers identified: ASML, Corning, Murata Manufacturing, Qualcomm, Sony Semiconductor Solutions
- False positives: None
- False negatives: None
- Malformed entities surviving: None

## Before / After Metrics

| Metric | Before | After |
|---|---:|---:|
| Apple expected Tier-1 suppliers found | 1-2 / 7 from stale cache traces | 7 / 7 |
| Named malformed entities surviving | 6 known examples observed in cache | 0 in benchmark run |
| Benchmark average precision | Not measured | 1.000 |
| Benchmark average recall | Not measured | 1.000 |
