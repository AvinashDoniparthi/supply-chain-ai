from __future__ import annotations

from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from providers.llm_provider import get_llm, resolve_provider


class GeneratedSupplierCandidate(BaseModel):
    name: str = Field(description="Potential supplier company name")
    rationale: str = Field(description="Short rationale based only on the supplied context")


class GeneratedSupplierCandidates(BaseModel):
    candidates: List[GeneratedSupplierCandidate] = Field(default_factory=list)


candidate_generation_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a supply-chain research assistant. Propose potential component-specific "
        "supplier company candidates using only the company, product, and component context. "
        "Do not use or assume any reference dataset, expected supplier list, or hidden ground truth. "
        "Candidates are hypotheses only and are not verified suppliers. Return valid JSON only.",
    ),
    (
        "user",
        "Company: {company}\nProduct: {product}\nComponent: {component}\n\n"
        "Return a JSON object with a candidates array. Each item must contain exactly a company "
        "name and a brief rationale. Return an empty array when no plausible candidate can be proposed.\n\n"
        "{format_instructions}",
    ),
])


def get_candidate_generation_chain(provider: str, model: str):
    config = resolve_provider(provider=provider, model=model)
    llm = get_llm(provider=config.provider, model=config.model)
    parser = PydanticOutputParser(pydantic_object=GeneratedSupplierCandidates)
    return candidate_generation_prompt | llm | parser, parser
