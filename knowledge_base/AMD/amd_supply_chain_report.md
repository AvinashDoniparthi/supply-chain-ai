# AMD

## Executive Summary
- RAG EXECUTIVE SUMMARY
- AMD's retrieved supply-chain health is Good with a score of 78.8/100. Key retrieved suppliers include Taiwan Semiconductor Manufacturing Company, GlobalFoundries, Samsung Electronics. The main retrieved risk themes are Geopolitical risk for TSMC, Geopolitical risk for ASE Technology.
- SUPPLY CHAIN HEALTH
- - Score: 78.8
- - Status: Good
- - Interpretation: AMD's supply chain appears good overall. 2 supplier(s) face high or critical risk exposure. Verification quality is high (12/14 suppliers verified).
- KEY SUPPLIERS
- - Taiwan Semiconductor Manufacturing Company (Tier 1, Semiconductor foundry)
- - GlobalFoundries (Tier 1, Semiconductor foundry)
- - Samsung Electronics (Tier 1, Semiconductor manufacturing)
- - ASE Technology (Tier 1, Semiconductor packaging)
- - Amkor Technology (Tier 1, Semiconductor packaging)
- - ASML (Tier 2, EUV lithography systems)
- - Applied Materials (Tier 2, Semiconductor manufacturing equipment)
- - Lam Research (Tier 2, Etch and deposition tools)
- TIER DEPENDENCIES
- - AMD -> Taiwan Semiconductor Manufacturing Company
- - AMD -> GlobalFoundries
- - AMD -> Samsung Electronics
- - AMD -> ASE Technology
- - AMD -> Amkor Technology
- - AMD -> Taiwan Semiconductor Manufacturing Company -> ASML
- - AMD -> Taiwan Semiconductor Manufacturing Company -> Applied Materials
- - AMD -> Taiwan Semiconductor Manufacturing Company -> Lam Research
- MAJOR RISKS
- - Risk: Geopolitical
- Affected supplier/path: AMD -> Taiwan Semiconductor Manufacturing Company
- Severity: High
- Reason: Taiwan geopolitical exposure through TSMC. Affected path: AMD -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
- - Risk: Geopolitical
- Affected supplier/path: AMD -> ASE Technology
- Severity: High
- Reason: Taiwan geopolitical exposure through ASE Technology. Affected path: AMD -> ASE Technology. Reason: ASE Technology is located in Taiwan, a high-tension geopolitical region.
- RECOMMENDATIONS
- - Investigate geopolitical exposure for TSMC: Taiwan geopolitical exposure through TSMC. Affected path: AMD -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
- DATA LIMITATIONS
- - No missing retrieved sections identified.

## Supply Chain Health
- Health Score: 78.80
- Status: Good
- Supplier Count: 14
- Verified Supplier Count: 12

## Tier 1 Suppliers
- Supplier: Amkor Technology
  - Parent: AMD
  - Relationship Path: AMD -> Amkor Technology
  - Relationship: supplier
  - Confidence: 0.88
  - Verification: Verified (0.90)
- Supplier: ASE Technology
  - Parent: AMD
  - Relationship Path: AMD -> ASE Technology
  - Relationship: supplier
  - Confidence: 0.83
  - Verification: Verified (0.90)
- Supplier: GlobalFoundries
  - Parent: AMD
  - Relationship Path: AMD -> GlobalFoundries
  - Relationship: supplier
  - Confidence: 0.90
  - Verification: Verified (0.90)
- Supplier: Samsung Electronics
  - Parent: AMD
  - Relationship Path: AMD -> Samsung Electronics
  - Relationship: supplier
  - Confidence: 0.88
  - Verification: Verified (0.90)
- Supplier: Taiwan Semiconductor Manufacturing Company
  - Parent: AMD
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company
  - Relationship: supplier
  - Confidence: 0.85
  - Verification: Verified (0.91)

## Tier 2 Suppliers
- Supplier: Applied Materials
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> Applied Materials
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: ASML
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> ASML
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Lam Research
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> Lam Research
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Murata Manufacturing
  - Parent: Samsung Electronics
  - Relationship Path: AMD -> Samsung Electronics -> Murata Manufacturing
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Sony Semiconductor Solutions
  - Parent: Samsung Electronics
  - Relationship Path: AMD -> Samsung Electronics -> Sony Semiconductor Solutions
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Tokyo Electron
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> Tokyo Electron
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)

## Tier 3 Suppliers
- Supplier: Carl Zeiss SMT
  - Parent: ASML
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> ASML -> Carl Zeiss SMT
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Trumpf
  - Parent: ASML
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> ASML -> Trumpf
  - Relationship: upstream_supplier
  - Confidence: 0.61
  - Verification: Not verified (0.35)
- Supplier: VDL ETG
  - Parent: ASML
  - Relationship Path: AMD -> Taiwan Semiconductor Manufacturing Company -> ASML -> VDL ETG
  - Relationship: upstream_supplier
  - Confidence: 0.63
  - Verification: Not verified (0.35)

## Major Risks
- Risk Type: Geopolitical
  - Affected Supplier: TSMC
  - Severity: High
  - Reason: Taiwan geopolitical exposure through TSMC. Affected path: AMD -> TSMC. Reason: TSMC is located in Hsinchu, Taiwan, a high-tension geopolitical region.
  - Mitigation: Identify and qualify alternative suppliers in diverse geographic regions.
- Risk Type: Geopolitical
  - Affected Supplier: ASE Technology
  - Severity: High
  - Reason: Taiwan geopolitical exposure through ASE Technology. Affected path: AMD -> ASE Technology. Reason: ASE Technology is located in Taiwan, a high-tension geopolitical region.
  - Mitigation: Identify and qualify alternative suppliers in diverse geographic regions.

## Critical Suppliers
- GlobalFoundries (High, 0.81)
- Samsung Electronics (High, 0.81)
- Taiwan Semiconductor Manufacturing Company (High, 0.81)
- Applied Materials (High, 0.72)
- Tokyo Electron (High, 0.72)
- Amkor Technology (Medium, 0.63)
- ASE Technology (Medium, 0.63)
- Murata Manufacturing (Medium, 0.63)
- ASML (Medium, 0.50)
- Carl Zeiss SMT (Medium, 0.50)
- Lam Research (Medium, 0.50)
- Sony Semiconductor Solutions (Medium, 0.50)
- Trumpf (Low, 0.19)
- VDL ETG (Low, 0.19)

## Verification Summary
- Total Verifications: 14
- Verified Supplier Count: 12
- Not Verified Count: 2
- Verified Suppliers: Taiwan Semiconductor Manufacturing Company, GlobalFoundries, Samsung Electronics, ASE Technology, Amkor Technology, ASML, Applied Materials, Lam Research, Tokyo Electron, Murata Manufacturing, Sony Semiconductor Solutions, Carl Zeiss SMT

## Confidence Summary
- Amkor Technology: 0.88
- Applied Materials: 0.90
- ASE Technology: 0.83
- ASML: 0.90
- Carl Zeiss SMT: 0.90
- GlobalFoundries: 0.90
- Lam Research: 0.89
- Murata Manufacturing: 0.89
- Samsung Electronics: 0.88
- Sony Semiconductor Solutions: 0.89
- Taiwan Semiconductor Manufacturing Company: 0.85
- Tokyo Electron: 0.89
- Trumpf: 0.61
- VDL ETG: 0.63

## Report Metadata
- Generated Timestamp: 2026-07-09T08:28:19.831105+00:00
- Mode: rag
- Max Depth: 3
