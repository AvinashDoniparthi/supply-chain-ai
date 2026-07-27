# Apple Verification-Filtering Fix Report

Date: 2026-07-24

## Pipeline change

The verification boundary now:

1. Preserves pre-verification candidates in `AgentState.discovered_suppliers`.
2. Stores retained verification results in `AgentState.verification_results`.
3. Stores discarded candidates and reasons in `AgentState.discarded_suppliers`.
4. Replaces `AgentState.suppliers` with verified-only suppliers before risk analysis.
5. Indexes only retained suppliers/results for downstream RAG analysis.

Accepted verification threshold: `confidence_score >= 0.55`, matching the existing verification aggregator threshold.

## Smoke-test comparison

| Mode | Provider / model | Discovered | Discarded | Retained | Risk inputs | Runtime | Result |
|---|---|---:|---:|---:|---:|---:|---|
| llm | Google / `gemini-2.5-flash` | 11 | 1 | 10 | 10 | 20.2s | Passed |
| rag | Google + ChromaDB / `gemini-2.5-flash` | 12 | 2 | 10 | 10 | Not emitted by RAG report | Passed with existing RAG warnings |
| slm | Ollama / `gemma3:4b` | 11 | 1 | 10 | 10 | 2.8s | Passed |

## Discarded suppliers

- `VDL ETG` — `company_exists=False` in llm, rag, and slm.
- `Trumpf` — `company_exists=False` in rag; it was already removed by relationship filtering in llm/slm before verification.

No discarded supplier appeared in the post-verification supplier list, risk-analysis input, retained verification results, or final supplier network.

## Retained verified suppliers

All three corrected runs retained the same ten suppliers:

1. TSMC
2. Hon Hai Precision Industry
3. Pegatron
4. Broadcom
5. Murata Manufacturing
6. ASML
7. Applied Materials
8. Lam Research
9. Tokyo Electron
10. Carl Zeiss SMT

## Risk analysis inputs

Risk analysis received exactly the ten retained suppliers in every mode. It produced three high geopolitical risks involving TSMC, Hon Hai Precision Industry, and Pegatron. No discarded supplier was evaluated.

## Final executive report supplier list

The final reports list only the ten retained suppliers above. The LLM and SLM reports include Carl Zeiss SMT as the only Tier-3 supplier; the RAG report likewise lists only retained suppliers and retained tier paths.

## Validation

- Full test suite: **174 passed**, 10 warnings, 79 subtests passed.
- Corrected Apple smoke matrix: all three workflows reached `ANALYSIS COMPLETE`.
- Existing RAG metadata-filter warnings and Gemini/network fallback remain, but they do not reintroduce discarded suppliers.

## Logs

- [llm log](./apple_llm.log)
- [rag log](./apple_rag.log)
- [slm log](./apple_slm.log)
