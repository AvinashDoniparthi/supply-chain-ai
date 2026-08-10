# Product Benchmark Sample Summary

- Sample ID: 20260802
- Sample Label: final_llm_gemini
- Output Folder: database/benchmarks/product_level/sample_20260802_final_llm_gemini
- Companies: 6
- Modes: llm
- Max Depth: 3
- Skip News: True
- Fast Benchmark: False
- Total rows: 17
- Successful rows: 2
- Failed rows: 0
- Quota-exhausted rows: 1

Quantitative evaluation was performed only for Tier 1 supplier relationships because reliable public ground-truth data is available primarily at Tier 1. Tier 2 and Tier 3 supplier relationships were evaluated qualitatively through discovered supply-chain paths, verification status, and confidence scores.

## Per-Company Rows
- Apple: 4 rows
- Samsung: 4 rows
- NVIDIA: 2 rows
- AMD: 2 rows
- Intel: 2 rows
- Tesla: 3 rows

## Quota Exhausted
- Tesla / Battery Cells / llm: Relationship classification quota exhausted for Mitsubishi Materials: Error calling model 'gemini-2.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, model: gemini-2.5-flash\nPlease retry in 52.406928187s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash'}, 'quotaValue': '5'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '52s'}]}}; Relationship classification quota exhausted for Ganfeng Lithium: Error calling model 'gemini-2.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, model: gemini-2.5-flash\nPlease retry in 52.406928187s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash'}, 'quotaValue': '5'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '52s'}]}}; Relationship classification quota exhausted for Tianqi Lithium: Error calling model 'gemini-2.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, model: gemini-2.5-flash\nPlease retry in 52.406928187s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash'}, 'quotaValue': '5'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '52s'}]}}

## Tier 2 and Tier 3 Discovery Statistics
- Tier 2 rows with discovery output: 1
- Tier 3 rows with discovery output: 0
- Tier 2 output includes discovered suppliers, verified suppliers, confidence, and paths.

## Warnings
- WARNING: Component outputs appear identical. Component context may not be influencing discovery.
- WARNING: Component outputs appear identical. Component context may not be influencing discovery.
- WARNING: Component outputs appear identical. Component context may not be influencing discovery.
- WARNING: Component outputs appear identical. Component context may not be influencing discovery.