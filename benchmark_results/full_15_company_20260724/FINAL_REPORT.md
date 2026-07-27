# Full 15-Company / 3-Mode Benchmark

Date: 2026-07-24

Companies: Apple, Samsung, Nvidia, AMD, Intel, Microsoft, Tesla, TSMC, ASML, Foxconn, Micron Technology, Logitech, Sonos, GoPro, Framework Computer

## Verdict

**BENCHMARK COMPLETE BUT FALLBACK-DOMINATED**

## Integrity

- Runs expected: 45; logs parsed: 45.
- Workflow completion: 100%.
- Downstream filtering invariants: PASS.
- Network/model/retrieval warning-bearing runs: 45/27/9.
- Benchmark interpretation: fallback-assisted performance; primary model performance is not directly measurable because model invocations failed or were not invoked in insufficient-data cases.

## Master comparison

| Company | Mode | Provider | Model | Runtime | Wall Runtime | Completed | Discovered | Discarded | Retained | Risk Inputs | Risks | Verification | Primary Model | Fallback | Retrieval | Final Report |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| AMD | llm | Gemini | `gemini-2.5-flash` | 22.2s | 27s | yes | 13 | 1 | 12 | 12 | 2 | 12/13 (92%) | no | yes | not applicable | yes |
| AMD | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 30s | yes | 14 | 2 | 12 | 12 | 2 | 12/14 (86%) | no | yes | yes | yes |
| AMD | slm | Ollama | `gemma3:4b` | 3.2s | 8s | yes | 13 | 1 | 12 | 12 | 2 | 12/13 (92%) | no | yes | not applicable | yes |
| Apple | llm | Gemini | `gemini-2.5-flash` | 19.6s | 25s | yes | 11 | 1 | 10 | 10 | 3 | 10/11 (91%) | no | yes | not applicable | yes |
| Apple | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 29s | yes | 12 | 2 | 10 | 10 | 3 | 10/12 (83%) | no | yes | yes | yes |
| Apple | slm | Ollama | `gemma3:4b` | 3.3s | 8s | yes | 11 | 1 | 10 | 10 | 3 | 10/11 (91%) | no | yes | not applicable | yes |
| ASML | llm | Gemini | `gemini-2.5-flash` | 4.9s | 9s | yes | 2 | 1 | 1 | 1 | 0 | 1/2 (50%) | no | yes | not applicable | yes |
| ASML | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 12s | yes | 3 | 2 | 1 | 1 | 0 | 1/3 (33%) | no | yes | yes | yes |
| ASML | slm | Ollama | `gemma3:4b` | 0.4s | 5s | yes | 2 | 1 | 1 | 1 | 0 | 1/2 (50%) | no | yes | not applicable | yes |
| Foxconn | llm | Gemini | `gemini-2.5-flash` | 28.4s | 33s | yes | 15 | 4 | 11 | 11 | 1 | 11/15 (73%) | no | yes | not applicable | yes |
| Foxconn | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 36s | yes | 16 | 4 | 12 | 12 | 1 | 12/16 (75%) | no | yes | yes | yes |
| Foxconn | slm | Ollama | `gemma3:4b` | 5.0s | 10s | yes | 15 | 4 | 11 | 11 | 1 | 11/15 (73%) | no | yes | not applicable | yes |
| Framework Computer | llm | Gemini | `gemini-2.5-flash` | 0.2s | 4s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Framework Computer | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| Framework Computer | slm | Ollama | `gemma3:4b` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| GoPro | llm | Gemini | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| GoPro | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| GoPro | slm | Ollama | `gemma3:4b` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Intel | llm | Gemini | `gemini-2.5-flash` | 10.9s | 15s | yes | 6 | 1 | 5 | 6 | 0 | 5/6 (83%) | no | yes | not applicable | yes |
| Intel | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 19s | yes | 7 | 2 | 5 | 6 | 0 | 5/7 (71%) | no | yes | yes | yes |
| Intel | slm | Ollama | `gemma3:4b` | 0.9s | 5s | yes | 6 | 1 | 5 | 6 | 0 | 5/6 (83%) | no | yes | not applicable | yes |
| Logitech | llm | Gemini | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Logitech | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| Logitech | slm | Ollama | `gemma3:4b` | 0.2s | 4s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Micron Technology | llm | Gemini | `gemini-2.5-flash` | 0.4s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Micron Technology | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.4s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| Micron Technology | slm | Ollama | `gemma3:4b` | 0.4s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Microsoft | llm | Gemini | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Microsoft | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| Microsoft | slm | Ollama | `gemma3:4b` | 0.2s | 4s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Nvidia | llm | Gemini | `gemini-2.5-flash` | 20.0s | 25s | yes | 10 | 1 | 9 | 9 | 1 | 9/10 (90%) | no | yes | not applicable | yes |
| Nvidia | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 27s | yes | 12 | 2 | 10 | 10 | 1 | 10/12 (83%) | no | yes | yes | yes |
| Nvidia | slm | Ollama | `gemma3:4b` | 2.2s | 7s | yes | 10 | 1 | 9 | 9 | 1 | 9/10 (90%) | no | yes | not applicable | yes |
| Samsung | llm | Gemini | `gemini-2.5-flash` | 22.3s | 27s | yes | 12 | 1 | 11 | 11 | 0 | 11/12 (92%) | no | yes | not applicable | yes |
| Samsung | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 28s | yes | 13 | 2 | 11 | 11 | 0 | 11/13 (85%) | no | yes | yes | yes |
| Samsung | slm | Ollama | `gemma3:4b` | 2.6s | 7s | yes | 12 | 1 | 11 | 11 | 0 | 11/12 (92%) | no | yes | not applicable | yes |
| Sonos | llm | Gemini | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Sonos | rag | Gemini + ChromaDB | `gemini-2.5-flash` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | no | yes |
| Sonos | slm | Ollama | `gemma3:4b` | 0.2s | 5s | yes | 0 | 0 | 0 | 0 | 0 | Not assessed | not invoked | no | not applicable | yes |
| Tesla | llm | Gemini | `gemini-2.5-flash` | 14.9s | 20s | yes | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | no | yes | not applicable | yes |
| Tesla | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 20s | yes | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | no | yes | yes | yes |
| Tesla | slm | Ollama | `gemma3:4b` | 1.3s | 6s | yes | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | no | yes | not applicable | yes |
| TSMC | llm | Gemini | `gemini-2.5-flash` | 13.4s | 18s | yes | 7 | 1 | 6 | 6 | 0 | 6/7 (86%) | no | yes | not applicable | yes |
| TSMC | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 19s | yes | 8 | 2 | 6 | 6 | 0 | 6/8 (75%) | no | yes | yes | yes |
| TSMC | slm | Ollama | `gemma3:4b` | 1.0s | 6s | yes | 7 | 1 | 6 | 6 | 0 | 6/7 (86%) | no | yes | not applicable | yes |

## Mode-level summaries

| Mode | Completion | Primary model success | Fallback usage | Avg runtime (emitted only) | Avg discovered | Avg retained | Avg discard rate | Avg risks | Avg verification confidence | Insufficient data | System failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| llm | 100.0% | 0.0% (9 invoked) | 60.0% | 10.533s | 5.6 | 4.6 | 21.4% | 0.533 | 78.6% | 6 | 0 |
| rag | 100.0% | 0.0% (9 invoked) | 60.0% | 0.233s | 6.2 | 4.733 | 28.7% | 0.533 | 71.3% | 6 | 0 |
| slm | 100.0% | 0.0% (9 invoked) | 60.0% | 1.42s | 5.6 | 4.6 | 21.4% | 0.533 | 78.6% | 6 | 0 |

## Cross-mode supplier inconsistencies

- Nvidia: llm: ASML, Applied Materials, Carl Zeiss SMT, Lam Research, Murata Manufacturing, SK hynix, Sony Semiconductor Solutions., TSMC, Tokyo Electron | rag: ASML, Applied Materials, Carl Zeiss SMT, Lam Research, Murata Manufacturing, SK hynix, Samsung Electronics, Sony Semiconductor Solutions, TSMC, Tokyo Electron | slm: ASML, Applied Materials, Carl Zeiss SMT, Lam Research, Murata Manufacturing, SK hynix, Sony Semiconductor Solutions., TSMC, Tokyo Electron
- Foxconn: llm: ASML, Apple Inc., Applied Materials, Broadcom, Lam Research, Murata Manufacturing, Qualcomm, Samsung Electronics, Sony Semiconductor Solutions, TSMC, Tokyo Electron | rag: ASML, Apple Inc., Applied Materials, Broadcom, Corning, Lam Research, Murata Manufacturing, Qualcomm, Samsung Electronics, Sony Semiconductor Solutions, TSMC, Tokyo Electron | slm: ASML, Apple Inc., Applied Materials, Broadcom, Lam Research, Murata Manufacturing, Qualcomm, Samsung Electronics, Sony Semiconductor Solutions, TSMC, Tokyo Electron

## Fallback events by stage and reason

- executive report: Gemini generation failed: 9 runs
- heuristic fallback: 27 runs
- relationship classification: model invocation failed: 27 runs
- retrieved-context fallback: 9 runs

## Insufficient-public-data cases

- Framework Computer / llm: workflow completed with zero suppliers discovered
- Framework Computer / rag: workflow completed with zero suppliers discovered
- Framework Computer / slm: workflow completed with zero suppliers discovered
- Microsoft / llm: workflow completed with zero suppliers discovered
- Microsoft / rag: workflow completed with zero suppliers discovered
- Microsoft / slm: workflow completed with zero suppliers discovered
- GoPro / llm: workflow completed with zero suppliers discovered
- GoPro / rag: workflow completed with zero suppliers discovered
- GoPro / slm: workflow completed with zero suppliers discovered
- Logitech / llm: workflow completed with zero suppliers discovered
- Logitech / rag: workflow completed with zero suppliers discovered
- Logitech / slm: workflow completed with zero suppliers discovered
- Micron Technology / llm: workflow completed with zero suppliers discovered
- Micron Technology / rag: workflow completed with zero suppliers discovered
- Micron Technology / slm: workflow completed with zero suppliers discovered
- Sonos / llm: workflow completed with zero suppliers discovered
- Sonos / rag: workflow completed with zero suppliers discovered
- Sonos / slm: workflow completed with zero suppliers discovered

## Genuine system failures

None identified

## Warning and error categories

- Network: 45 runs recorded DNS/name-resolution or sandbox network-permission warnings. These affected Google/Wikipedia access and Ollama access.
- Model: 27 runs attempted model-backed relationship classification and recorded invocation errors; none of those invocations succeeded.
- Retrieval: 9 RAG runs recorded Chroma metadata-filter warnings. Nine RAG runs also recorded Gemini report-generation skips.
- Verification: discarded suppliers were recorded with reasons, but none reached risk analysis or the final retained supplier list.
- Insufficient public data: 18 completed runs had zero discovered suppliers. These are classified separately from system failures.

## Verification and downstream checks

- No discarded supplier entered risk analysis in any run.
- Risk input count equaled retained supplier count in all runs.
- No discarded supplier appeared in the final retained supplier list.
- `discovered_suppliers` and `discarded_suppliers` were preserved in the post-fix workflow output.

## Primary versus fallback interpretation

- Primary model invocation success is tracked separately from workflow completion.
- Fallback output is not counted as primary-model success.
- The benchmark is a mixture operationally, but because all model-backed supplier-classification runs used fallback and insufficient-data runs did not invoke the model, the aggregate result is fallback-dominated rather than direct model performance.

## Per-run logs

- [amd_llm.log](./amd_llm.log)
- [amd_rag.log](./amd_rag.log)
- [amd_slm.log](./amd_slm.log)
- [apple_llm.log](./apple_llm.log)
- [apple_rag.log](./apple_rag.log)
- [apple_slm.log](./apple_slm.log)
- [asml_llm.log](./asml_llm.log)
- [asml_rag.log](./asml_rag.log)
- [asml_slm.log](./asml_slm.log)
- [foxconn_llm.log](./foxconn_llm.log)
- [foxconn_rag.log](./foxconn_rag.log)
- [foxconn_slm.log](./foxconn_slm.log)
- [framework_computer_llm.log](./framework_computer_llm.log)
- [framework_computer_rag.log](./framework_computer_rag.log)
- [framework_computer_slm.log](./framework_computer_slm.log)
- [gopro_llm.log](./gopro_llm.log)
- [gopro_rag.log](./gopro_rag.log)
- [gopro_slm.log](./gopro_slm.log)
- [intel_llm.log](./intel_llm.log)
- [intel_rag.log](./intel_rag.log)
- [intel_slm.log](./intel_slm.log)
- [logitech_llm.log](./logitech_llm.log)
- [logitech_rag.log](./logitech_rag.log)
- [logitech_slm.log](./logitech_slm.log)
- [micron_technology_llm.log](./micron_technology_llm.log)
- [micron_technology_rag.log](./micron_technology_rag.log)
- [micron_technology_slm.log](./micron_technology_slm.log)
- [microsoft_llm.log](./microsoft_llm.log)
- [microsoft_rag.log](./microsoft_rag.log)
- [microsoft_slm.log](./microsoft_slm.log)
- [nvidia_llm.log](./nvidia_llm.log)
- [nvidia_rag.log](./nvidia_rag.log)
- [nvidia_slm.log](./nvidia_slm.log)
- [samsung_llm.log](./samsung_llm.log)
- [samsung_rag.log](./samsung_rag.log)
- [samsung_slm.log](./samsung_slm.log)
- [sonos_llm.log](./sonos_llm.log)
- [sonos_rag.log](./sonos_rag.log)
- [sonos_slm.log](./sonos_slm.log)
- [tesla_llm.log](./tesla_llm.log)
- [tesla_rag.log](./tesla_rag.log)
- [tesla_slm.log](./tesla_slm.log)
- [tsmc_llm.log](./tsmc_llm.log)
- [tsmc_rag.log](./tsmc_rag.log)
- [tsmc_slm.log](./tsmc_slm.log)
