# Multi-Company Validation Benchmark

Date: 2026-07-24  
Companies: Apple, Foxconn, Tesla  
Modes: llm, rag, slm  

All runs used the existing command-line workflow and configuration. No prompts, thresholds, providers, models, agents, retrieval settings, or fallback logic were changed for this benchmark.

## Comparison table

| Company | Mode | Provider | Model | Runtime | Discovered | Discarded | Retained | Risk inputs | Risks | Verification confidence | Complete |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Apple | llm | Gemini | `gemini-2.5-flash` | 20.4s | 11 | 1 | 10 | 10 | 3 | 10/11 (91%) | Yes |
| Apple | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 12 | 2 | 10 | 10 | 3 | 10/12 (83%) | Yes |
| Apple | slm | Ollama | `gemma3:4b` | 3.2s | 11 | 1 | 10 | 10 | 3 | 10/11 (91%) | Yes |
| Foxconn | llm | Gemini | `gemini-2.5-flash` | 28.0s | 15 | 4 | 11 | 11 | 1 | 11/15 (73%) | Yes |
| Foxconn | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 16 | 4 | 12 | 12 | 1 | 12/16 (75%) | Yes |
| Foxconn | slm | Ollama | `gemma3:4b` | 4.7s | 15 | 4 | 11 | 11 | 1 | 11/15 (73%) | Yes |
| Tesla | llm | Gemini | `gemini-2.5-flash` | 13.9s | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | Yes |
| Tesla | rag | Gemini + ChromaDB | `gemini-2.5-flash` | Not emitted | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | Yes |
| Tesla | slm | Ollama | `gemma3:4b` | 1.2s | 8 | 4 | 4 | 4 | 1 | 4/8 (50%) | Yes |

RAG mode does not emit the standard performance-timing section; therefore its runtime is recorded as not emitted rather than inferred.

## Discarded suppliers and reasons

- Apple: `VDL ETG` — `company_exists=False` in llm/rag/slm; RAG additionally discarded `Trumpf` for `company_exists=False`.
- Foxconn: `E Ink Corporation`, `Netronix Inc`, `Geely Holding Group`, and `PTT Public Co` — each `company_exists=False` in all three modes.
- Tesla: `Sumitomo Metal Mining`, `Mitsubishi Materials`, `Ganfeng Lithium`, and `Tianqi Lithium` — each `company_exists=False` in all three modes.

## Retained supplier lists

Apple retained the same 10 suppliers in every mode:

`TSMC`, `Hon Hai Precision Industry`, `Pegatron`, `Broadcom`, `Murata Manufacturing`, `ASML`, `Applied Materials`, `Lam Research`, `Tokyo Electron`, `Carl Zeiss SMT`.

Foxconn retained:

- llm/slm: `Apple Inc.`, `TSMC`, `Broadcom`, `Samsung Electronics`, `ASML`, `Applied Materials`, `Lam Research`, `Tokyo Electron`, `Qualcomm`, `Murata Manufacturing`, `Sony Semiconductor Solutions`.
- rag: the same list plus `Corning`.

Tesla retained the same four suppliers in every mode:

`Panasonic`, `Contemporary Amperex Technology Co. Limited`, `LG Energy Solution`, `Samsung SDI`.

## Downstream invariant checks

All 9 logs reached `ANALYSIS COMPLETE`. Risk-analysis input count equaled retained-supplier count in every run. An automated scan of each risk-analysis input block found zero discarded supplier names. Final supplier lists contained only retained suppliers. `discovered_suppliers` and `discarded_suppliers` were present in the post-fix report output and preserved discovery/discard metrics.

No supplier with `company_exists=False`, `verification_status=FAILED`, `verified=False`, or verification confidence below `0.55` entered risk analysis.

## Inconsistent classifications across modes

1. Apple RAG discovered one additional candidate and discarded `Trumpf`; llm/slm discarded only `VDL ETG`.
2. Foxconn RAG discovered and retained `Corning`; llm/slm did not. This produced 16 discovered / 12 retained in RAG versus 15 discovered / 11 retained in llm/slm.
3. Tesla had consistent retained and discarded classifications across all modes.

## Warnings and errors by category

### Network

- Gemini and Wikipedia requests encountered DNS/name-resolution failures for `generativelanguage.googleapis.com` and `en.wikipedia.org`.
- SLM local Ollama calls encountered sandbox `Operation not permitted` connection errors in relationship classification.

### Retrieval

- RAG runs logged Chroma metadata-filter warnings: `Expected where to have exactly one operator` for combined `company_key` and `source_type` filters.

### Model

- Gemini relationship-classification calls failed when the Google endpoint was unreachable.
- Ollama relationship-classification calls failed under the sandbox connection restriction.

### Fallback

- All modes used relationship-classification heuristic fallback where model calls failed.
- RAG runs skipped LLM report generation and used the existing retrieved-context fallback when Gemini was unreachable.

### Verification

- Verification discarded the suppliers listed above, all with `company_exists=False`.
- No verification failure propagated into risk analysis or the retained supplier network.

## Fallback usage

Fallback logic was used in all 9 runs for relationship classification. RAG fallback report generation was used in all 3 RAG runs.

## Readiness verdict

**READY FOR FULL BENCHMARK**

All 9 workflows completed, and no discarded supplier reached downstream stages. RAG runtime instrumentation and existing network/retrieval warnings remain benchmark observability limitations, not filtering-invariant failures.

## Full logs

- [Apple llm](./Apple_llm.log) · [Apple rag](./Apple_rag.log) · [Apple slm](./Apple_slm.log)
- [Foxconn llm](./Foxconn_llm.log) · [Foxconn rag](./Foxconn_rag.log) · [Foxconn slm](./Foxconn_slm.log)
- [Tesla llm](./Tesla_llm.log) · [Tesla rag](./Tesla_rag.log) · [Tesla slm](./Tesla_slm.log)
