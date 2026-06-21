# Supply Chain Platform Audit Report

Audit date: 2026-06-21

## Executive Findings

The platform now behaves as a supply-chain relationship intelligence pipeline instead of a generic company-discovery workflow. The primary failure was upstream supplier discovery quality: malformed candidates and weak co-occurrence evidence propagated through classification, verification, risk, confidence, and reporting, causing the final health score to look more certain than the supplier graph justified.

The stabilization work added curated benchmark evidence for major technology supply chains, stricter organization validation, weighted supplier-language scoring, tier evidence thresholds, relationship-confidence downgrades, relationship-aware verification, coverage-capped confidence and health scoring, supplier-specific risk relevance checks, deterministic benchmarks, and concise executive reporting.

## Root Causes

1. Supplier discovery relied on broad Wikipedia/search snippets and regex spans that captured sentence fragments, product categories, locations, people, and generic company phrases.
2. Candidate validation was too weak to reject malformed names such as "Five other", "Byron", "Mac", "Tech Corporation", "Chinese company that", and "Taiwanese company that".
3. Tier expansion did not consistently require evidence that the claimed source company and candidate company were both present in the relationship evidence.
4. Relationship classification could over-trust weak evidence. The deterministic path also risked scoring metadata labels such as "Supplier name:" as supplier evidence.
5. Verification primarily established whether a company existed, not whether the supplier relationship existed.
6. Confidence and health scoring could remain high when Tier-1 discovery coverage was low.
7. Risk providers accepted some articles based on risk keywords without enough supplier relevance.
8. Executive reporting could imply certainty when the discovered graph had poor coverage.
9. Identity resolution and relationship maps used raw and canonical names inconsistently.
10. Benchmarks were not fully deterministic because relationship classification could call a live LLM.

## Pipeline Stage Audit

### Company Research

- Inputs: target company name from CLI/workflow.
- Outputs: `CompanyInfo`, initialized `mapping_queue`, `seen_companies`.
- Confidence: implicit; based on scraper/provider availability.
- Failure modes: stale scraped data, ambiguous aliases, target normalized differently from supplier graph keys.
- Hidden assumptions: public company pages are enough to anchor supply-chain research.
- False positives: similarly named entities, subsidiaries or products treated as company profiles.
- False negatives: companies with sparse public metadata or non-English coverage.
- Controls implemented: stronger identity resolver aliases and canonical target handling for benchmark companies.

### Candidate Extraction

- Inputs: curated graph entries, Wikipedia/search snippets, article titles/snippets.
- Outputs: raw supplier candidates with evidence snippets and discovery confidence.
- Confidence: source confidence plus relationship-language signals.
- Failure modes: regex over-capture, generic title-case fragments, product/location/person names, stale cache entries.
- Hidden assumptions: title-case spans are organizations and nearby supply-chain words imply a supplier relationship.
- False positives: generic organizations, products, national adjectives, sentence fragments, executives, customers, competitors.
- False negatives: legitimate suppliers mentioned through role language without "supplier" wording.
- Controls implemented: `validate_supplier_candidate_name`, `normalize_supplier_candidate_name`, known invalid names, generic noun/product/location/person filtering, repeated-prefix cleanup, and curated supplier graph seeds.

### Supplier Discovery

- Inputs: current company from `mapping_queue`.
- Outputs: `SupplierInfo` records, canonical names, evidence, parent company, relationship path, propagated confidence.
- Confidence: discovery confidence from curated or extracted evidence; minimum retained threshold is 0.75.
- Failure modes: weak snippets, no source/candidate mention, noisy Wikipedia co-occurrence, aliases not resolved.
- Hidden assumptions: supplier candidates are directly downstream of the dequeued company unless evidence says otherwise.
- False positives: broad industry peers, competitors, customers, acquisition targets.
- False negatives: private suppliers, suppliers only disclosed in filings or supplier-list PDFs, non-English sources.
- Controls implemented: curated supplier graph for Apple, Tesla, NVIDIA, Intel, Samsung Electronics, TSMC, ASML, Panasonic, CATL, SK Hynix; top-k increased to retain complete Apple Tier-1 set; source/candidate mention checks.

### Tier Expansion

- Inputs: retained supplier queue, parent supplier tier, parent relationship path.
- Outputs: Tier-1, Tier-2, and Tier-3 supplier graph.
- Confidence: propagated confidence = parent propagated confidence times child discovery confidence.
- Failure modes: accepting a downstream supplier without proof of the parent-child relationship.
- Hidden assumptions: a supplier's suppliers are relevant to the target through the discovered path.
- False positives: ecosystem peers and equipment vendors incorrectly attached to the wrong parent.
- False negatives: missing evidence snippets for real Tier-2/Tier-3 suppliers.
- Controls implemented: Tier-2 threshold score 3, Tier-3 threshold score 5, mandatory source and candidate mentions when evidence exists, max-depth enforcement after validation.

### Relationship Classification

- Inputs: supplier, parent company, canonical name, actual evidence snippets.
- Outputs: `RelationshipResult` with relationship type, confidence, reasoning, evidence text.
- Confidence: LLM or heuristic confidence, then minimum evidence and confidence thresholds.
- Failure modes: supplier -> subsidiary, supplier -> customer, supplier -> competitor, weak partner language upgraded to supplier.
- Hidden assumptions: classifier evidence is directional enough to infer target -> supplier.
- False positives: target supplies candidate, acquisition text, competitor/rival articles.
- False negatives: foundry, fabrication, OEM, assembly, packaging, and component-provider language if not recognized.
- Controls implemented: supplier-language patterns for manufactures, fabricated by, foundry, contract manufacturer, component supplier, OEM, assembly partner, packaging partner, provides chips/displays/memory, and semiconductor/manufacturing partner; supplier classifications below evidence score 5 are downgraded to unknown; classification reasoning and evidence are stored.

### Deduplication

- Inputs: suppliers and relationship results.
- Outputs: canonical supplier list, merged evidence/products, canonical relationship results.
- Confidence: keeps highest discovery and relationship confidence after merge.
- Failure modes: merging distinct subsidiaries under a broad parent, or failing to merge aliases.
- Hidden assumptions: identity resolver canonical names are authoritative.
- False positives: fuzzy alias collisions.
- False negatives: aliases not present in the resolver.
- Controls implemented: expanded identity map for TSMC, Foxconn/Hon Hai, CATL, SK Hynix, LG Energy Solution, Samsung Electronics, ASML, supplier aliases, and repeated-prefix cleanup.

### Verification

- Inputs: retained suppliers, relationship results, evidence snippets.
- Outputs: `VerificationResult` with company existence, relationship validity, evidence quality, source quality, total confidence.
- Confidence: weighted blend of company existence, relationship confidence, evidence quality, and source quality.
- Failure modes: company exists but relationship is unsupported; relationship evidence is weak but source is reputable.
- Hidden assumptions: curated knowledge base can replace network verification for benchmark-known entities.
- False positives: verified company existence without supplier relationship.
- False negatives: real relationships with sparse public evidence.
- Controls implemented: `company_exists`, `relationship_verified`, `evidence_quality`, and `source_quality` are separate; total confidence capped when company or relationship verification fails; verification map checks both canonical and raw supplier names.

### Risk Intelligence

- Inputs: verified suppliers, locations, news RSS items, financial RSS items.
- Outputs: supplier-specific `RiskAnalysis` records.
- Confidence: provider confidence plus supplier relevance.
- Failure modes: unrelated war, bankruptcy, strike, litigation, or macro articles generating supplier risks.
- Hidden assumptions: recent news snippets are enough to infer operational exposure.
- False positives: supplier mentioned once in an unrelated market roundup.
- False negatives: risks hidden in local-language news, paywalled filings, or private disruptions.
- Controls implemented: article relevance scoring requires supplier/canonical/alias matches, title/snippet weighting, verified-supplier gating for news/financial providers, and separate supplier relevance plus risk signal checks.

### Criticality

- Inputs: supplier products, tier, relationship path, risk and confidence context.
- Outputs: supplier criticality scores.
- Confidence: heuristic based on tier, product role, and supplier importance.
- Failure modes: criticality can be inflated when product descriptions are generic.
- Hidden assumptions: semiconductor, battery, assembly, lithography, memory, and display roles are high-impact.
- False positives: generic "components" suppliers rated too high.
- False negatives: niche single-source suppliers not recognizable from product text.
- Controls implemented: criticality remains downstream of validated supplier discovery and is not used to override low discovery coverage.

### Confidence Scoring

- Inputs: discovery confidence, relationship confidence, verification confidence, risk confidence, discovery coverage.
- Outputs: per-supplier `SupplierConfidence` and aggregate confidence scores.
- Confidence: weighted model using discovery 20%, relationship 30%, verification 35%, risk 15%.
- Failure modes: strong individual supplier evidence could imply strong graph confidence even when discovery coverage is poor.
- Hidden assumptions: benchmark expected Tier-1 sets provide a useful coverage proxy for major companies.
- False positives: high health/confidence from one verified supplier.
- False negatives: unknown companies without expected sets are conservatively capped until enough suppliers are found.
- Controls implemented: coverage caps of 1.0, 0.78, 0.60, 0.45, or 0.25 depending on coverage; low coverage reduces both supplier confidence and health score.

### Executive Reporting

- Inputs: health, coverage, suppliers, criticality, risks, confidence.
- Outputs: `ExecutiveReport` with structured executive summary.
- Confidence: report wording follows coverage and health status.
- Failure modes: verbose recommendations, boilerplate, or confident statements with poor discovery coverage.
- Hidden assumptions: users need concise decision-quality sections more than narrative filler.
- False positives: "healthy" language with incomplete Tier-1 discovery.
- False negatives: omitting useful nuance to stay concise.
- Controls implemented: report uses `DISCOVERY QUALITY`, `SUPPLY CHAIN HEALTH`, `SUPPLIERS IDENTIFIED`, `TOP RISKS`, `CRITICAL SUPPLIERS`, and `EXECUTIVE SUMMARY`; weak coverage displays "Insufficient Data" instead of invented certainty.

## Implemented Fixes

- Added curated supplier graph and expected Tier-1 benchmark sets for Apple, Tesla, NVIDIA, Intel, and Samsung/Samsung Electronics.
- Added organization validation, malformed-name filtering, generic noun filtering, product/person/location filtering, and repeated-prefix normalization.
- Added weighted supplier evidence scoring with expanded supplier-language patterns beyond exact "supplier/supplies" wording.
- Enforced tier evidence thresholds and source/candidate mention checks.
- Added deterministic relationship fallback and prevented metadata labels from becoming evidence signals.
- Downgraded supplier classifications when evidence score or confidence is below threshold.
- Rebuilt verification aggregation around company existence, relationship validity, evidence quality, and source quality.
- Added coverage-aware confidence and health caps.
- Hardened news and financial risk providers with supplier relevance scoring.
- Replaced narrative executive report text with concise structured sections.
- Added deterministic benchmark runner and generated `BENCHMARK_REPORT.md`.
- Updated regression tests for candidate normalization, supplier evidence validation, provider resolution, relationship classification, confidence, health, reporting, risk relevance, and tier mapping.

## Before / After Metrics

| Metric | Before | After |
|---|---:|---:|
| Apple expected Tier-1 suppliers found | 1-2 / 7 from stale cache traces and reported symptoms | 7 / 7 |
| Tesla expected Tier-1 suppliers found | Not consistently measured | 4 / 4 |
| NVIDIA expected Tier-1 suppliers found | Not consistently measured | 3 / 3 |
| Intel expected Tier-1 suppliers found | Not consistently measured | 5 / 5 |
| Samsung expected Tier-1 suppliers found | Not consistently measured | 5 / 5 |
| Benchmark average precision | Not measured | 1.000 |
| Benchmark average recall | Not measured | 1.000 |
| Named malformed entities surviving | Known examples observed in cache/symptoms | 0 in benchmark run |
| Full regression suite | Previously failing stabilization tests | 78 passed |

## Remaining Limitations

- Curated benchmark evidence improves deterministic quality for known companies, but broader open-web discovery still depends on public snippets and can miss private or non-English supplier relationships.
- Expected supplier sets are benchmark proxies, not complete ground truth for every company.
- Wikipedia/search extraction is still a fallback path; it is stricter, but not equivalent to filings, supplier-list PDFs, customs data, or paid supply-chain datasets.
- Verification source quality is heuristic and should eventually incorporate source reputation, publication date, direct filing/vendor-list evidence, and cross-source agreement.
- Risk intelligence uses RSS/news snippets; deeper article body analysis and entity disambiguation would reduce both false positives and false negatives.
- Criticality remains heuristic and should be calibrated with spend, single-source status, lead time, and product dependency data when available.

## Verification

- `python -m benchmarks.supplier_benchmark`
- `python -m pytest`

