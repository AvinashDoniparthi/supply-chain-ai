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

For LLM/RAG comparison:

```bash
python3 main.py --company AMD --mode llm
python3 main.py --company AMD --mode rag
```

## Current Status

The framework supports supplier discovery, verification, risk scoring, and executive reporting for major companies such as Apple, AMD, NVIDIA, Qualcomm, and Dell. The project is currently being extended to compare LLM-only reasoning against RAG-based evidence retrieval.

## Purpose

This project was built as an AI-powered supply chain intelligence system to demonstrate how LLMs, agents, and retrieval-based methods can be used for supplier mapping, risk detection, and decision-support reporting.
