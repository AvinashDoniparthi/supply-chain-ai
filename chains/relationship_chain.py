import json

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from providers.llm_provider import get_llm, resolve_provider
from prompts.relationship_prompt import relationship_prompt
import logging

logger = logging.getLogger(__name__)

class RelationshipClassification(BaseModel):
    relationship: str = Field(description="The classified relationship: supplier, upstream_supplier, customer, competitor, partner, unrelated, or product_or_brand")
    confidence: float = Field(description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Brief explanation for the classification")


class RelationshipBatchItem(BaseModel):
    """One model-produced classification in a relationship batch."""

    supplier_name: str | None = Field(default=None)
    relationship: str | None = None
    confidence: object | None = None
    reasoning: object | None = None


class RelationshipBatchClassification(BaseModel):
    """Structured response containing classifications for a supplier batch."""

    results: list[RelationshipBatchItem] = Field(default_factory=list)


class RelationshipBatchOutputParser(PydanticOutputParser):
    """Parse the canonical batch object, accepting a bare JSON result list too."""

    def parse(self, text: str) -> RelationshipBatchClassification:
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise OutputParserException(
                "Invalid JSON for relationship batch classification",
                llm_output=text,
            ) from exc

        if isinstance(payload, list):
            payload = {"results": payload}
        elif not isinstance(payload, dict):
            raise OutputParserException(
                "Relationship batch classification must be a JSON object or list",
                llm_output=text,
            )

        try:
            return RelationshipBatchClassification.model_validate(payload)
        except Exception as exc:
            raise OutputParserException(
                "Invalid relationship batch classification schema",
                llm_output=text,
            ) from exc


relationship_batch_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a supply chain intelligence analyst. Classify each supplier only "
        "from its supplied evidence. Return exactly one result for every input item "
        "and copy each input supplier_name exactly.",
    ),
    (
        "user",
        """Classify every supplier in this batch. Each input item includes its target company,
candidate supplier name, and evidence.

{batch_evidence}

Allowed relationship labels: supplier, upstream_supplier, customer, partner,
competitor, unrelated, product_or_brand.

Return one result per input item. Each result must contain the exact input
supplier_name, relationship, confidence (0 to 1), and reasoning.

Return one JSON object with a top-level "results" array. Do not return the
array by itself. Do not use markdown fences or add any other prose.

{format_instructions}""",
    ),
])

def get_relationship_chain(provider=None, model=None):
    config = resolve_provider(provider=provider, model=model)
    logger.debug(
        "[RELATIONSHIP CHAIN] Initializing provider=%s model=%s",
        config.provider,
        config.model,
    )
    llm = get_llm(provider=config.provider, model=config.model)
    parser = PydanticOutputParser(pydantic_object=RelationshipClassification)
    
    # We use a partial to inject format_instructions later or we can do it during invocation
    chain = relationship_prompt | llm | parser
    logger.debug(
        "[RELATIONSHIP CHAIN] Initialization succeeded provider=%s model=%s",
        config.provider,
        config.model,
    )
    return chain


def get_relationship_batch_chain(provider=None, model=None):
    """Build the structured chain used for batched relationship classification."""

    config = resolve_provider(provider=provider, model=model)
    logger.debug(
        "[RELATIONSHIP BATCH CHAIN] Initializing provider=%s model=%s",
        config.provider,
        config.model,
    )
    llm = get_llm(provider=config.provider, model=config.model)
    parser = RelationshipBatchOutputParser(pydantic_object=RelationshipBatchClassification)
    chain = relationship_batch_prompt | llm | parser
    logger.debug(
        "[RELATIONSHIP BATCH CHAIN] Initialization succeeded provider=%s model=%s",
        config.provider,
        config.model,
    )
    return chain
