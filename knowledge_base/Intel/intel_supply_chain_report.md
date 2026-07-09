# Intel

## Executive Summary
- RAG EXECUTIVE SUMMARY
- Intel's retrieved supply-chain health is Good with a score of 77.8/100. Key retrieved suppliers include ASML, Applied Materials, Lam Research.
- SUPPLY CHAIN HEALTH
- - Score: 77.8
- - Status: Good
- - Interpretation: Intel's supply chain appears good overall. No major operational disruptions were detected. Verification quality is medium (5/7 suppliers verified).
- KEY SUPPLIERS
- - ASML (Tier 1, EUV lithography systems)
- - Applied Materials (Tier 1, Semiconductor manufacturing equipment)
- - Lam Research (Tier 1, Etch and deposition tools)
- - Tokyo Electron (Tier 1, Semiconductor production tools)
- - Carl Zeiss SMT (Tier 2, Lithography optics)
- - Trumpf (Tier 2, Laser systems)
- - VDL ETG (Tier 2, Mechatronic modules)
- TIER DEPENDENCIES
- - Intel -> ASML
- - Intel -> Applied Materials
- - Intel -> Lam Research
- - Intel -> Tokyo Electron
- - Intel -> ASML -> Carl Zeiss SMT
- - Intel -> ASML -> Trumpf
- - Intel -> ASML -> VDL ETG
- MAJOR RISKS
- - Information not available in retrieved context.
- RECOMMENDATIONS
- - Information not available in retrieved context.
- DATA LIMITATIONS
- - Recommendation context was not retrieved.

## Supply Chain Health
- Health Score: 77.80
- Status: Good
- Supplier Count: 7
- Verified Supplier Count: 5

## Tier 1 Suppliers
- Supplier: Applied Materials
  - Parent: Intel
  - Relationship Path: Intel -> Applied Materials
  - Relationship: supplier
  - Confidence: 0.78
  - Verification: Verified (0.90)
- Supplier: ASML
  - Parent: Intel
  - Relationship Path: Intel -> ASML
  - Relationship: supplier
  - Confidence: 0.78
  - Verification: Verified (0.91)
- Supplier: Lam Research
  - Parent: Intel
  - Relationship Path: Intel -> Lam Research
  - Relationship: supplier
  - Confidence: 0.78
  - Verification: Verified (0.91)
- Supplier: Tokyo Electron
  - Parent: Intel
  - Relationship Path: Intel -> Tokyo Electron
  - Relationship: supplier
  - Confidence: 0.78
  - Verification: Verified (0.91)

## Tier 2 Suppliers
- Supplier: Carl Zeiss SMT
  - Parent: ASML
  - Relationship Path: Intel -> ASML -> Carl Zeiss SMT
  - Relationship: upstream_supplier
  - Confidence: 0.78
  - Verification: Verified (0.91)
- Supplier: Trumpf
  - Parent: ASML
  - Relationship Path: Intel -> ASML -> Trumpf
  - Relationship: upstream_supplier
  - Confidence: 0.61
  - Verification: Not verified (0.35)
- Supplier: VDL ETG
  - Parent: ASML
  - Relationship Path: Intel -> ASML -> VDL ETG
  - Relationship: upstream_supplier
  - Confidence: 0.63
  - Verification: Not verified (0.35)

## Tier 3 Suppliers
- None verified

## Major Risks
- None verified

## Critical Suppliers
- Applied Materials (High, 0.81)
- Tokyo Electron (High, 0.81)
- ASML (Medium, 0.59)
- Lam Research (Medium, 0.59)
- Carl Zeiss SMT (Medium, 0.50)
- Trumpf (Low, 0.19)
- VDL ETG (Low, 0.19)

## Verification Summary
- Total Verifications: 7
- Verified Supplier Count: 5
- Not Verified Count: 2
- Verified Suppliers: ASML, Applied Materials, Lam Research, Tokyo Electron, Carl Zeiss SMT

## Confidence Summary
- Applied Materials: 0.78
- ASML: 0.78
- Carl Zeiss SMT: 0.78
- Lam Research: 0.78
- Tokyo Electron: 0.78
- Trumpf: 0.61
- VDL ETG: 0.63

## Report Metadata
- Generated Timestamp: 2026-07-09T13:27:04.839803+00:00
- Mode: rag
- Max Depth: 3
