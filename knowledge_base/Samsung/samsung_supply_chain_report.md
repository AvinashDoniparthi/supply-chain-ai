# Samsung

## Executive Summary
- RAG EXECUTIVE SUMMARY
- Samsung's retrieved supply-chain health is Good with a score of 82.6/100. Key retrieved suppliers include ASML, Corning Inc., Qualcomm.
- SUPPLY CHAIN HEALTH
- - Score: 82.6
- - Status: Good
- - Interpretation: Samsung's supply chain appears good overall. No major operational disruptions were detected. Verification quality is high (11/13 suppliers verified).
- KEY SUPPLIERS
- - ASML (Tier 1, EUV lithography systems)
- - Corning Inc. (Tier 1, Cover glass)
- - Qualcomm (Tier 1, Mobile chipsets)
- - Murata Manufacturing (Tier 1, Capacitors)
- - Sony Semiconductor Solutions (Tier 1, Image sensors)
- - Carl Zeiss SMT (Tier 2, Lithography optics)
- - Trumpf (Tier 2, Laser systems)
- - VDL ETG (Tier 2, Mechatronic modules)
- TIER DEPENDENCIES
- - Samsung -> ASML
- - Samsung -> Corning Inc.
- - Samsung -> Qualcomm
- - Samsung -> Murata Manufacturing
- - Samsung -> Sony Semiconductor Solutions
- - Samsung -> ASML -> Carl Zeiss SMT
- - Samsung -> ASML -> Trumpf
- - Samsung -> ASML -> VDL ETG
- MAJOR RISKS
- - Information not available in retrieved context.
- RECOMMENDATIONS
- - Information not available in retrieved context.
- DATA LIMITATIONS
- - No missing retrieved sections identified.

## Supply Chain Health
- Health Score: 82.60
- Status: Good
- Supplier Count: 13
- Verified Supplier Count: 11

## Tier 1 Suppliers
- Supplier: ASML
  - Parent: Samsung
  - Relationship Path: Samsung -> ASML
  - Relationship: supplier
  - Confidence: 0.90
  - Verification: Verified (0.90)
- Supplier: Corning Inc.
  - Parent: Samsung
  - Relationship Path: Samsung -> Corning Inc.
  - Relationship: supplier
  - Confidence: 0.89
  - Verification: Verified (0.90)
- Supplier: Murata Manufacturing
  - Parent: Samsung
  - Relationship Path: Samsung -> Murata Manufacturing
  - Relationship: supplier
  - Confidence: 0.89
  - Verification: Verified (0.90)
- Supplier: Qualcomm
  - Parent: Samsung
  - Relationship Path: Samsung -> Qualcomm
  - Relationship: supplier
  - Confidence: 0.89
  - Verification: Verified (0.90)
- Supplier: Sony Semiconductor Solutions
  - Parent: Samsung
  - Relationship Path: Samsung -> Sony Semiconductor Solutions
  - Relationship: supplier
  - Confidence: 0.88
  - Verification: Verified (0.90)

## Tier 2 Suppliers
- Supplier: Amkor Technology
  - Parent: Qualcomm
  - Relationship Path: Samsung -> Qualcomm -> Amkor Technology
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.89)
- Supplier: Carl Zeiss SMT
  - Parent: ASML
  - Relationship Path: Samsung -> ASML -> Carl Zeiss SMT
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Taiwan Semiconductor Manufacturing Company
  - Parent: Qualcomm
  - Relationship Path: Samsung -> Qualcomm -> Taiwan Semiconductor Manufacturing Company
  - Relationship: upstream_supplier
  - Confidence: 0.88
  - Verification: Verified (0.89)
- Supplier: Trumpf
  - Parent: ASML
  - Relationship Path: Samsung -> ASML -> Trumpf
  - Relationship: upstream_supplier
  - Confidence: 0.61
  - Verification: Not verified (0.35)
- Supplier: VDL ETG
  - Parent: ASML
  - Relationship Path: Samsung -> ASML -> VDL ETG
  - Relationship: upstream_supplier
  - Confidence: 0.63
  - Verification: Not verified (0.35)

## Tier 3 Suppliers
- Supplier: Applied Materials
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Samsung -> Qualcomm -> Taiwan Semiconductor Manufacturing Company -> Applied Materials
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)
- Supplier: Lam Research
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Samsung -> Qualcomm -> Taiwan Semiconductor Manufacturing Company -> Lam Research
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)
- Supplier: Tokyo Electron
  - Parent: Taiwan Semiconductor Manufacturing Company
  - Relationship Path: Samsung -> Qualcomm -> Taiwan Semiconductor Manufacturing Company -> Tokyo Electron
  - Relationship: upstream_supplier
  - Confidence: 0.89
  - Verification: Verified (0.91)

## Major Risks
- None verified

## Critical Suppliers
- Qualcomm (High, 0.81)
- Applied Materials (High, 0.72)
- Murata Manufacturing (High, 0.72)
- Tokyo Electron (High, 0.72)
- Amkor Technology (High, 0.71)
- Taiwan Semiconductor Manufacturing Company (Medium, 0.63)
- ASML (Medium, 0.58)
- Corning Inc. (Medium, 0.58)
- Sony Semiconductor Solutions (Medium, 0.58)
- Carl Zeiss SMT (Medium, 0.50)
- Lam Research (Medium, 0.50)
- Trumpf (Low, 0.19)
- VDL ETG (Low, 0.19)

## Verification Summary
- Total Verifications: 13
- Verified Supplier Count: 11
- Not Verified Count: 2
- Verified Suppliers: ASML, Corning Inc., Qualcomm, Murata Manufacturing, Sony Semiconductor Solutions, Carl Zeiss SMT, Amkor Technology, Taiwan Semiconductor Manufacturing Company, Applied Materials, Lam Research, Tokyo Electron

## Confidence Summary
- Amkor Technology: 0.89
- Applied Materials: 0.90
- ASML: 0.90
- Carl Zeiss SMT: 0.90
- Corning Inc.: 0.89
- Lam Research: 0.89
- Murata Manufacturing: 0.89
- Qualcomm: 0.89
- Sony Semiconductor Solutions: 0.88
- Taiwan Semiconductor Manufacturing Company: 0.88
- Tokyo Electron: 0.89
- Trumpf: 0.61
- VDL ETG: 0.63

## Report Metadata
- Generated Timestamp: 2026-07-09T06:45:03.926609+00:00
- Mode: rag
- Max Depth: 3
