# Thesis Benchmark Summary

This benchmark runs the full supply-chain intelligence pipeline in both `llm` and `rag` modes with identical settings (`max_depth=3`, `skip_news=True`).

## Execution

- Companies: Apple, Samsung, Nvidia, AMD, Intel, Microsoft, Tesla, TSMC, ASML, Foxconn, Micron Technology, Logitech, Sonos, GoPro, Framework Computer
- Modes: llm, rag
- Runs attempted: 30
- Successful runs: 20
- Insufficient-data runs: 10
- Failed runs: 0

## CSV Schema

| Column | Description |
|---|---|
| `company` | Company analyzed |
| `mode` | Execution mode (`llm` or `rag`) |
| `evaluation_status` | Benchmark evaluation class (`success`, `insufficient_public_supply_chain_data`, or `system_failure`) |
| `evaluation_note` | Human-readable evaluation note |
| `status` | Run status (`success` or `failed`) |
| `error_message` | Failure message when the run did not complete |
| `reference_source` | Source used to define the benchmark reference set |
| `reference_supplier_count` | Number of reference suppliers for scoring |
| `max_depth` | Configured discovery depth |
| `skip_news` | Whether news/risk news ingestion was disabled |
| `accuracy_score` | F1-style accuracy on reference Tier-1 suppliers, percent |
| `precision` | Tier-1 precision, percent |
| `recall` | Tier-1 recall, percent |
| `hallucination_rate` | False-positive rate on Tier-1 suppliers, percent |
| `retrieval_grounding_score` | Composite grounding score, percent |
| `verification_success_rate` | Verified suppliers divided by supplier count, percent |
| `average_confidence_score` | Average supplier confidence, percent |
| `runtime_seconds` | Wall-clock runtime |
| `token_usage` | Estimated token usage |
| `estimated_api_cost` | Estimated API cost from token usage |
| `estimated_energy_consumption` | Estimated energy usage in kWh |
| `coverage_score` | Reference Tier-1 coverage, percent |
| `tier_discovery_effectiveness` | Weighted depth-discovery score, percent |
| `supplier_count` | Total suppliers retained by the pipeline |
| `tier1_count` | Tier-1 suppliers |
| `tier2_count` | Tier-2 suppliers |
| `tier3_count` | Tier-3 suppliers |
| `verified_supplier_count` | Verified suppliers |
| `risk_count` | Generated risk records |
| `retrieved_context_chunks` | RAG context chunks attached |
| `health_score` | Final health score |
| `health_status` | Final health status |

## Methodology

| Metric | Formula | Notes |
|---|---|---|
| Accuracy Score | `2 * precision * recall / (precision + recall)` | F1-style score for Tier-1 supplier recovery. |
| Precision | `true_positives / discovered_suppliers` | Measures how many retained suppliers are in the benchmark reference set. |
| Recall | `true_positives / reference_suppliers` | Measures how many reference suppliers were recovered. |
| Hallucination Rate | `false_positives / discovered_suppliers` | False positives divided by discovered suppliers; if no suppliers are discovered, the rate is `0`. |
| Retrieval Grounding Score | `supported_final_claims / total_final_claims` | RAG-only claim support against retrieved context chunks; LLM-only is `0`. |
| Verification Success Rate | `verified_supplier_count / supplier_count` | Percentage of retained suppliers that passed verification. |
| Average Confidence Score | `mean(final_confidence) * 100` | Mean supplier confidence across the final retained supplier set. |
| Runtime Seconds | `wall_clock_end - wall_clock_start` | Full `run_analysis()` duration for the company/mode pair. |
| Token Usage | `estimated_prompt_tokens + estimated_output_tokens` | Consistent proxy estimate derived from LLM call count, output size, and RAG context size. |
| Estimated API Cost | `token_usage / 1000 * cost_per_1k_tokens` | Uses the fixed benchmark cost proxy. |
| Estimated Energy Consumption | `runtime_seconds * 0.000015 + token_usage * 0.000000004` | Hybrid runtime-plus-token proxy; higher token usage increases energy. |
| Coverage Score | `recall * 100` | Tier-1 coverage against the benchmark reference set. |
| Tier Discovery Effectiveness | `100 * (0.7 * weighted_depth_ratio + 0.3 * precision)` | Weighted depth ratio uses `tier1 + 0.5*tier2 + 0.25*tier3`. |

Reference policy: benchmark ground truth comes from repository graphs/history where available, plus static/manual benchmark priors for missing companies. All 15 requested companies are included in the run matrix.

## Evaluation Case Classification

Total Companies Evaluated: 15
Successful Evaluations: 10
Insufficient Public Data Cases: 5
System Failures: 0

Insufficient Public Data Cases:
- Micron Technology
- Logitech
- Sonos
- GoPro
- Framework Computer

These are not counted as system failures. They represent cases where public supply-chain evidence from the configured sources was too limited for meaningful supplier discovery.

## Evaluated-Only Averages

| Metric | LLM | RAG |
|---|---:|---:|
| Success Rate | 100.00% | 100.00% |
| Accuracy Score | 52.34 | 53.62 |
| Precision | 44.70 | 43.01 |
| Recall | 72.48 | 79.14 |
| Hallucination Rate | 45.30 | 46.99 |
| Retrieval Grounding Score | 0.00 | 90.00 |
| Verification Success Rate | 70.73 | 67.39 |
| Average Confidence Score | 72.88 | 70.35 |
| Runtime Seconds | 3.84 | 3.58 |
| Token Usage | 10911 | 23989 |
| Estimated API Cost | 0.0082 | 0.0180 |
| Estimated Energy Consumption | 0.000101 | 0.000149 |
| Coverage Score | 72.48 | 79.14 |
| Tier Discovery Effectiveness | 74.08 | 75.90 |

## Comparison Table

| Metric | LLM Avg | RAG Avg | Winner |
|---|---:|---:|---|
| Accuracy Score | 52.34 | 53.62 | RAG |
| Precision | 44.70 | 43.01 | LLM |
| Recall | 72.48 | 79.14 | RAG |
| Hallucination Rate | 45.30 | 46.99 | LLM |
| Retrieval Grounding Score | 0.00 | 90.00 | RAG |
| Verification Success Rate | 70.73 | 67.39 | LLM |
| Average Confidence Score | 72.88 | 70.35 | LLM |
| Latency | 3.84 | 3.58 | RAG |
| Token Usage | 10911 | 23989 | LLM |
| Estimated API Cost | 0.0082 | 0.0180 | LLM |
| Estimated Energy Consumption | 0.000101 | 0.000149 | LLM |
| Coverage Score | 72.48 | 79.14 | RAG |
| Tier Discovery Effectiveness | 74.08 | 75.90 | RAG |

## Highlights

- Accuracy: RAG is better
- Hallucination: LLM is better
- Latency: RAG is better
- Cost: LLM is better
- Coverage: RAG is better
- Tier Discovery: RAG is better

## Company Comparison

| Company | LLM Accuracy | RAG Accuracy | LLM Coverage | RAG Coverage | LLM Latency | RAG Latency |
|---|---:|---:|---:|---:|---:|---:|
| Apple | 55.56 | 52.63 | 71.43 | 71.43 | 5.39 | 6.00 |
| Samsung | 58.82 | 55.56 | 100.00 | 100.00 | 4.95 | 4.44 |
| Nvidia | 30.77 | 40.00 | 66.67 | 100.00 | 4.32 | 4.52 |
| AMD | 55.56 | 52.63 | 100.00 | 100.00 | 6.16 | 6.11 |
| Intel | 72.73 | 66.67 | 80.00 | 80.00 | 1.61 | 1.71 |
| Microsoft | 0.00 | 0.00 | 0.00 | 0.00 | 0.22 | 0.22 |
| Tesla | 66.67 | 72.73 | 100.00 | 100.00 | 3.48 | 2.16 |
| TSMC | 83.33 | 76.92 | 100.00 | 100.00 | 1.82 | 1.94 |
| ASML | 80.00 | 100.00 | 66.67 | 100.00 | 0.69 | 0.95 |
| Foxconn | 20.00 | 19.05 | 40.00 | 40.00 | 9.76 | 7.71 |
| Micron Technology | 0.00 | 0.00 | 0.00 | 0.00 | 0.54 | 0.55 |
| Logitech | 0.00 | 0.00 | 0.00 | 0.00 | 0.37 | 0.20 |
| Sonos | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 | 0.23 |
| GoPro | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 | 0.20 |
| Framework Computer | 0.00 | 0.00 | 0.00 | 0.00 | 0.21 | 0.21 |

## Thesis Conclusion

RAG improves retrieval grounding, recall, and coverage, but it does not dominate the benchmark overall because LLM-only wins the majority of the decision metrics that matter for thesis evaluation. Use RAG when grounded evidence is the priority; use LLM-only when balanced quality, lower token usage, and lower estimated cost matter more.

## Full Benchmark Averages

| Metric | LLM | RAG |
|---|---:|---:|
| Success Rate | 66.67% | 66.67% |
| Accuracy Score | 34.90 | 35.75 |
| Precision | 29.80 | 28.67 |
| Recall | 48.32 | 52.76 |
| Hallucination Rate | 30.20 | 31.33 |
| Retrieval Grounding Score | 0.00 | 60.00 |
| Verification Success Rate | 47.15 | 44.93 |
| Average Confidence Score | 48.58 | 46.90 |
| Runtime Seconds | 2.66 | 2.48 |
| Token Usage | 7279 | 16398 |
| Estimated API Cost | 0.0055 | 0.0123 |
| Estimated Energy Consumption | 0.000069 | 0.000103 |
| Coverage Score | 48.32 | 52.76 |
| Tier Discovery Effectiveness | 49.39 | 50.60 |
