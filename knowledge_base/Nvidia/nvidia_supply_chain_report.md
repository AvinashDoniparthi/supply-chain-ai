# Nvidia

## Executive Summary
- RAG EXECUTIVE SUMMARY
- Nvidia's retrieved supply-chain health is Good with a score of 80.0/100. Key retrieved suppliers include Taiwan Semiconductor Manufacturing Company, SK hynix, Samsung Electronics. The main retrieved risk themes are Geopolitical risk for TSMC.
- SUPPLY CHAIN HEALTH
- - Score: 80.0
- - Status: Good
- - Interpretation: Nvidia's supply chain appears good overall. 1 supplier(s) face high or critical risk exposure. Verification quality is high (10/12 suppliers verified).
- KEY SUPPLIERS
- - Taiwan Semiconductor Manufacturing Company (Tier 1, GPU fabrication)
- - SK hynix (Tier 1, HBM memory)
- - Samsung Electronics (Tier 1, Memory)
- - ASML (Tier 2, EUV lithography systems)
- - Applied Materials (Tier 2, Semiconductor manufacturing equipment)
- - Lam Research (Tier 2, Etch and deposition tools)
- - Tokyo Electron (Tier 2, Semiconductor production tools)
- - Murata Manufacturing (Tier 2, Capacitors)
- TIER DEPENDENCIES
- - Nvidia -> Taiwan Semiconductor Manufacturing Company
- - Nvidia -> SK hynix
- - Nvidia -> Samsung Electronics
- - Nvidia -> Taiwan Semiconductor Manufacturing Company -> ASML
- - Nvidia -> Taiwan Semiconductor Manufacturing Company -> Applied Materials
- - Nvidia -> Taiwan Semiconductor Manufacturing Company -> Lam Research
- - Nvidia -> Taiwan Semiconductor Manufacturing Company -> Tokyo Electron
- - Nvidia -> Samsung Electronics -> Murata Manufacturing
- MAJOR RISKS
- - Risk: Geopolitical
- Affected supplier/path: Nvidia -> Taiwan Semiconductor Manufacturing Company
- Severity: High
- Reason: Taiwan geopolitical exposure through TSMC. Affected path: Nvidia -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
- RECOMMENDATIONS
- - Investigate geopolitical exposure for TSMC: Taiwan geopolitical exposure through TSMC. Affected path: Nvidia -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
- DATA LIMITATIONS
- - No missing retrieved sections identified.

## Supply Chain Health
- Health Score: 80.00
- Status: Good
- Supplier Count: 12
- Verified Supplier Count: 10

## Tier 1 Suppliers
- Supplier: Samsung Electronics
  - Parent: Nvidia
  - Relationship Path: Nvidia -> Samsung Electronics
  - Relationship: supplier
  - Confidence: 0.86
  - Verification: Verified (0.88)
- Supplier: SK hynix
  - Parent: Nvidia
  - Relationship Path: Nvidia -> SK hynix
  - Relationship: supplier
  - Confidence: 0.90
  - Verification: Verified (0.90)
- Supplier: Taiwan Semiconductor Manufacturing Company
  - Parent: Nvidia
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company
  - Relationship: supplier
  - Confidence: 0.85
  - Verification: Verified (0.90)

## Tier 2 Suppliers
- Supplier: Applied Materials
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> Applied Materials
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: ASML
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> ASML
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Lam Research
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> Lam Research
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Murata Manufacturing
  - Parent: Samsung Electronics
  - Relationship Path: Nvidia -> Samsung Electronics -> Murata Manufacturing
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Sony Semiconductor Solutions
  - Parent: Samsung Electronics
  - Relationship Path: Nvidia -> Samsung Electronics -> Sony Semiconductor Solutions
  - Relationship: upstream_supplier
  - Confidence: 0.88
  - Verification: Verified (0.90)
- Supplier: Tokyo Electron
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> Tokyo Electron
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)

## Tier 3 Suppliers
- Supplier: Carl Zeiss SMT
  - Parent: ASML
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> ASML -> Carl Zeiss SMT
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Trumpf
  - Parent: ASML
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> ASML -> Trumpf
  - Relationship: upstream_supplier
  - Confidence: 0.61
  - Verification: Not verified (0.35)
- Supplier: VDL ETG
  - Parent: ASML
  - Relationship Path: Nvidia -> Taiwan Semiconductor Manufacturing Company -> ASML -> VDL ETG
  - Relationship: upstream_supplier
  - Confidence: 0.63
  - Verification: Not verified (0.35)

## Major Risks
- Risk Type: Geopolitical
  - Affected Supplier: TSMC
  - Severity: High
  - Reason: Taiwan geopolitical exposure through TSMC. Affected path: Nvidia -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
  - Mitigation: Identify and qualify alternative suppliers in diverse geographic regions.

## Critical Suppliers
- SK hynix (High, 0.81)
- Taiwan Semiconductor Manufacturing Company (High, 0.81)
- Samsung Electronics (High, 0.79)
- Applied Materials (High, 0.72)
- Tokyo Electron (High, 0.72)
- Murata Manufacturing (Medium, 0.63)
- ASML (Medium, 0.50)
- Carl Zeiss SMT (Medium, 0.50)
- Lam Research (Medium, 0.50)
- Sony Semiconductor Solutions (Low, 0.49)
- Trumpf (Low, 0.19)
- VDL ETG (Low, 0.19)

## Verification Summary
- Total Verifications: 12
- Verified Supplier Count: 10
- Not Verified Count: 2
- Verified Suppliers: Taiwan Semiconductor Manufacturing Company, SK hynix, Samsung Electronics, ASML, Applied Materials, Lam Research, Tokyo Electron, Murata Manufacturing, Sony Semiconductor Solutions, Carl Zeiss SMT

## Confidence Summary
- Applied Materials: 0.90
- ASML: 0.90
- Carl Zeiss SMT: 0.90
- Lam Research: 0.89
- Murata Manufacturing: 0.89
- Samsung Electronics: 0.86
- SK hynix: 0.90
- Sony Semiconductor Solutions: 0.88
- Taiwan Semiconductor Manufacturing Company: 0.85
- Tokyo Electron: 0.89
- Trumpf: 0.61
- VDL ETG: 0.63

## Report Metadata
- Generated Timestamp: 2026-07-09T07:16:11.570095+00:00
- Mode: rag
- Max Depth: 3
