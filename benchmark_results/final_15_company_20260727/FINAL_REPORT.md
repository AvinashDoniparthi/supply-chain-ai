# FINAL REPORT

Benchmark date: 2026-07-27
Fixed company list: Apple, Samsung, Nvidia, AMD, Intel, Microsoft, Tesla, TSMC, ASML, Foxconn, Micron Technology, Logitech, Sonos, GoPro, Framework Computer
Runs completed: 45/45

## Mode summary

| Mode | Provider/model | Workflow completion | Primary-model success | Fallback | Insufficient data | System failures | Avg runtime (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| llm | google:gemini-2.5-flash | 100.0% | 0.0% | 60.0% | 6 | 0 | 1.50 |
| rag | google:gemini-2.5-flash | 100.0% | 0.0% | 60.0% | 6 | 0 | 1.86 |
| slm | ollama:gemma3:4b | 100.0% | 0.0% | 60.0% | 6 | 0 | 1.47 |

## Integrity checks

- Risk input count equals retained supplier count: 45/45 runs.
- Discarded suppliers absent from retained set: 45/45 runs.
- Rejected suppliers absent from final report: 45/45 runs.
- Runtime recorded: 45/45 runs.
- Integrity failures: 0.

## Classification policy

- Fallback-generated output is not primary-model success.
- Insufficient public data is not a system failure.
- Failed workflow execution is a system failure.
- Missing runtime is reported as missing, never as zero.

## Artifacts

- One `.log` and one `.json` per run.
- `master_results.csv`, `company_summary.csv`, `mode_summary.csv`.
- `fallback_events.csv`, `insufficient_data_cases.csv`, `system_failures.csv.
