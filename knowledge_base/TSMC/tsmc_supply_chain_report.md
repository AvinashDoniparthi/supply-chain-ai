# TSMC

## Executive Summary
- Company: TSMC
- Mode: SLM
- Max Depth: 3
- Generated At: 2026-07-24 20:51:31 IST
- 1. EXECUTIVE SUMMARY
- TSMC has a moderately healthy supply chain with strong dependence on Applied Materials, Tokyo Electron, and ASML. The main concern is limited verification depth or supplier concentration.
- 2. DISCOVERY QUALITY
- Suppliers discovered: 7
- Suppliers retained after verification: 6
- Suppliers discarded: 1
- - VDL ETG: company_exists=False
- Coverage: High - 5 discovered Tier-1 suppliers identified.
- Verification-adjusted coverage: High (86%; 6/7 suppliers verified).
- 3. SUPPLY CHAIN HEALTH
- Status: Good - 85.4/100.
- Supplier Count: 6
- Critical Suppliers: 0
- High-Risk Suppliers: 0
- Summary: TSMC's supply chain appears good overall. No major operational disruptions were detected. Verification quality is high (6/7 suppliers verified).
- 4. SUPPLIER NETWORK
- 4.1 Tier 1 Suppliers
- TIER 1 SUPPLIERS
- Direct suppliers to TSMC
- 1. ASML
- Relationship : Supplier
- Confidence   : 0.91
- Verification : Verified (0.91)
- 2. Applied Materials
- Relationship : Supplier
- Confidence   : 0.87
- Verification : Verified (0.89)
- 3. Entegris
- Relationship : Supplier
- Confidence   : 0.88
- Verification : Verified (0.88)
- 4. Lam Research
- Relationship : Supplier
- Confidence   : 0.85
- Verification : Verified (0.88)
- 5. Tokyo Electron
- Relationship : Supplier
- Confidence   : 0.85
- Verification : Verified (0.88)
- 4.2 Tier 2 Suppliers
- TIER 2 SUPPLIERS
- Upstream suppliers connected through Tier 1 suppliers
- 1. Carl Zeiss SMT
- Parent       : ASML
- Path         : TSMC -> ASML -> Carl Zeiss SMT
- Relationship : Upstream Supplier
- Confidence   : 0.90
- Verification : Verified (0.91)
- 4.3 Tier 3 Suppliers
- TIER 3 SUPPLIERS
- Upstream suppliers connected through Tier 2 suppliers
- None identified
- 5. TOP RISKS
- High
- None identified
- Medium
- None identified
- Low
- None identified
- No supplier-specific risks detected
- 6. DATA QUALITY WARNINGS
- Low Verification Confidence
- None identified
- Failed Verification
- None identified
- Missing Verification Result
- None identified
- 7. CRITICAL SUPPLIERS
- 1. Applied Materials
- Tier         : 1
- Confidence   : 0.87
- Reason       : Supplier manufactures core semiconductor components and appears to be a sole-source dependency.
- 2. Tokyo Electron
- Tier         : 1
- Confidence   : 0.85
- Reason       : Supplier manufactures core semiconductor components and appears to be a sole-source dependency.

## Supply Chain Health
- Health Score: 85.40
- Status: Good
- Supplier Count: 6
- Verified Supplier Count: 6

## Tier 1 Suppliers
- Supplier: Applied Materials
  - Parent: TSMC
  - Relationship Path: TSMC -> Applied Materials
  - Relationship: supplier
  - Confidence: 0.87
  - Verification: Verified (0.89)
- Supplier: ASML
  - Parent: TSMC
  - Relationship Path: TSMC -> ASML
  - Relationship: supplier
  - Confidence: 0.91
  - Verification: Verified (0.91)
- Supplier: Entegris
  - Parent: TSMC
  - Relationship Path: TSMC -> Entegris
  - Relationship: supplier
  - Confidence: 0.88
  - Verification: Verified (0.88)
- Supplier: Lam Research
  - Parent: TSMC
  - Relationship Path: TSMC -> Lam Research
  - Relationship: supplier
  - Confidence: 0.85
  - Verification: Verified (0.88)
- Supplier: Tokyo Electron
  - Parent: TSMC
  - Relationship Path: TSMC -> Tokyo Electron
  - Relationship: supplier
  - Confidence: 0.85
  - Verification: Verified (0.88)

## Tier 2 Suppliers
- Supplier: Carl Zeiss SMT
  - Parent: ASML
  - Relationship Path: TSMC -> ASML -> Carl Zeiss SMT
  - Relationship: upstream_supplier
  - Confidence: 0.90
  - Verification: Verified (0.91)

## Tier 3 Suppliers
- None verified

## Major Risks
- None verified

## Critical Suppliers
- Applied Materials (High, 0.80)
- Tokyo Electron (High, 0.79)
- ASML (Medium, 0.59)
- Entegris (Medium, 0.57)
- Lam Research (Medium, 0.57)
- Carl Zeiss SMT (Medium, 0.50)

## Verification Summary
- Total Verifications: 6
- Verified Supplier Count: 6
- Not Verified Count: 0
- Verified Suppliers: ASML, Applied Materials, Lam Research, Tokyo Electron, Entegris, Carl Zeiss SMT

## Confidence Summary
- Applied Materials: 0.87
- ASML: 0.91
- Carl Zeiss SMT: 0.90
- Entegris: 0.88
- Lam Research: 0.85
- Tokyo Electron: 0.85

## Report Metadata
- Generated Timestamp: 2026-07-24T15:21:31.964670+00:00
- Mode: slm
- Max Depth: 3
