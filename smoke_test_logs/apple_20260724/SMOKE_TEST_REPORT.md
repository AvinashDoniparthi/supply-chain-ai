# Apple Supply-Chain Framework Smoke Test

Date: 2026-07-24

Commands executed (source unchanged):

- `python3 main.py --company Apple --mode llm --debug`
- `python3 main.py --company Apple --mode rag --debug`
- `python3 main.py --company Apple --mode slm --debug`

## Comparison

| Mode | Provider | Model | Runtime | Suppliers Found | Verified Suppliers | Risks | Success/Failure | Errors / warnings |
|---|---|---|---:|---:|---:|---:|---|---|
| llm | Google/Gemini | gemini-2.5-flash | 22.3s | 11 | 10/11 (91%) | 3 | Workflow success; smoke-test warning | Gemini/Wikipedia network resolution failures; VDL ETG failed verification |
| rag | Google/Gemini + ChromaDB | gemini-2.5-flash | not emitted in report; run completed | 12 | 10/12 (83% by count; report says high) | 3 | Workflow success with fallback | Chroma metadata-filter warnings; Gemini report call skipped due DNS; Trumpf and VDL ETG failed verification |
| slm | Ollama | gemma3:4b | 3.0s | 11 | 10/11 (91%) | 3 | Workflow success; smoke-test warning | Ollama relationship calls returned operation-not-permitted in this sandbox and fell back; Wikipedia network failures; VDL ETG failed verification |

## Pipeline checks

- Company research: completed for Apple in all modes using cached Apple company data.
- Supplier discovery: completed through Tier 3 and applied evidence filtering/top-K limits.
- Verification: completed in all modes.
- Risk analysis: completed; 3 high geopolitical risks were accepted in each run.
- Executive summary: completed. RAG used 35 retrieved context chunks and produced a fallback retrieved-context report when the Gemini generation call failed.
- Workflow completion: all runs reached `ANALYSIS COMPLETE`.
- Provider/model routing: confirmed in logs. LLM/RAG used Google `gemini-2.5-flash`; SLM used Ollama `gemma3:4b`.

## Hallucination check

**Failed / not clean.** The implementation retained suppliers that verification could not establish:

- `VDL ETG`: failed verification in all three runs; verification evidence reports `company_exists=False`.
- `Trumpf`: failed verification in RAG and SLM; it was removed during LLM deduplication.

Therefore, the smoke test cannot confirm that no hallucinated suppliers are introduced, even though unsupported candidates were rejected during discovery and the overall workflows completed.

## Raw logs

- [apple_llm.log](./apple_llm.log)
- [apple_rag.log](./apple_rag.log)
- [apple_slm.log](./apple_slm.log)
