# Supply Chain AI Intelligence Framework

A multi-agent AI framework for mapping and analyzing company supply chains across Tier 1, Tier 2, and Tier 3 suppliers. The system discovers supplier relationships, verifies evidence, classifies supplier roles, detects risks, scores confidence, and generates an executive-style supply chain report.

## Key Features

* Multi-agent workflow using LangGraph/LangChain
* Tier 1, Tier 2, and Tier 3 supplier discovery
* Supplier relationship classification
* Canonical supplier name resolution and alias handling
* Verification using evidence quality and company identity checks
* Risk analysis for geopolitical, financial, labor, and supply disruptions
* Confidence, criticality, and supply chain health scoring
* Clean executive dashboard output
* LLM-only and RAG mode support for comparison testing

## Tech Stack

* Python
* LangChain
* LangGraph
* Gemini API
* ChromaDB
* Pydantic
* Pytest

## Example Usage

```bash
python3 main.py --company Apple
python3 main.py --company AMD
python3 main.py --company Qualcomm
python3 main.py --company Dell
```

## Product Benchmark

Run the product-level benchmark as four separate timed samples so you can inspect each run independently:

```bash
python3 product_benchmark.py --sample-id 1 --sample-label morning
python3 product_benchmark.py --sample-id 2 --sample-label afternoon
python3 product_benchmark.py --sample-id 3 --sample-label evening
python3 product_benchmark.py --sample-id 4 --sample-label night
```

Each invocation runs the same matrix:

* Companies: Apple, Samsung, Nvidia, AMD, Intel, Tesla
* Modes: `llm`, `rag`
* Config: `max_depth=3`, `skip_news=True`

Outputs are written per sample:

```text
database/benchmarks/product_level/sample_1_morning/
database/benchmarks/product_level/sample_2_afternoon/
database/benchmarks/product_level/sample_3_evening/
database/benchmarks/product_level/sample_4_night/
```

Each sample folder contains:

* `apple_product_benchmark.csv`
* `samsung_product_benchmark.csv`
* `nvidia_product_benchmark.csv`
* `amd_product_benchmark.csv`
* `intel_product_benchmark.csv`
* `tesla_product_benchmark.csv`
* `master_results.csv`
* `sample_summary.md`

A global combined file is also rebuilt after each completed sample:

* `database/benchmarks/product_level/all_samples_master_results.csv`

Use `--overwrite` if you need to replace an existing sample folder with the same sample ID and label.

## HTTP API

Start the local API server:

```bash
python3 api_server.py --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Analyze a company:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"company":"Dell","execution_mode":"rag"}'
```

The response includes the full serialized analysis state, including the executive report, supply chain graph, risk assessments, and run metadata.

For LLM/RAG comparison:

```bash
python3 main.py --company AMD --mode llm
python3 main.py --company AMD --mode rag
```

## Current Status

The framework supports supplier discovery, verification, risk scoring, and executive reporting for major companies such as Apple, AMD, NVIDIA, Qualcomm, and Dell. The project is currently being extended to compare LLM-only reasoning against RAG-based evidence retrieval.

## Purpose

This project was built as an AI-powered supply chain intelligence system to demonstrate how LLMs, agents, and retrieval-based methods can be used for supplier mapping, risk detection, and decision-support reporting.
