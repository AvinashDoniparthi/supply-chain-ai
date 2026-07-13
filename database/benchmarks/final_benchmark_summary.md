# Final Benchmark Summary

- Total official benchmark runs: 4
- Total benchmark rows analyzed: 136
- Final summarized rows: 34

## Aggregate Means

| Metric | Mean |
|---|---:|
| Precision | 83.33 |
| Recall | 100.00 |
| F1 | 88.89 |
| Coverage | 100.00 |
| Hallucination Rate | 16.67 |
| Runtime (seconds) | 1.2396 |
| Confidence Score | 86.22 |

Precision, recall, F1, coverage, and hallucination means use quantitatively evaluable Tier-1 cases only. Standard deviations in the CSV are sample standard deviations across the four official runs.

## Best and Worst Performing Benchmark Cases

| Classification | Company | Product | Component | Mode | Precision | Recall | F1 | Hallucination Rate |
|---|---|---|---|---|---:|---:|---:|---:|
| Best | Apple | iPhone 16 Pro | Application Processor | LLM | 100 | 100 | 100 | 0 |
| Best | Apple | iPhone 16 Pro | Application Processor | RAG | 100 | 100 | 100 | 0 |
| Best | Samsung | Galaxy S25 Ultra | Application Processor | LLM | 100 | 100 | 100 | 0 |
| Best | Samsung | Galaxy S25 Ultra | Application Processor | RAG | 100 | 100 | 100 | 0 |
| Worst | Apple | iPhone 16 Pro | Assembly | LLM | 50 | 100 | 66.67 | 50 |
| Worst | Apple | iPhone 16 Pro | Assembly | RAG | 50 | 100 | 66.67 | 50 |

Performance classification is based on mean Tier-1 F1 score; ties are retained.

- Qualitative inconsistencies resolved by majority value: 0
