from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from providers.llm_provider import get_llm, resolve_provider
from prompts.relationship_prompt import relationship_prompt
import logging

logger = logging.getLogger(__name__)

class RelationshipClassification(BaseModel):
    relationship: str = Field(description="The classified relationship: supplier, upstream_supplier, customer, competitor, partner, unrelated, or product_or_brand")
    confidence: float = Field(description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Brief explanation for the classification")

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
