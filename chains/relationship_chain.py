from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from providers.llm_provider import get_llm
from prompts.relationship_prompt import relationship_prompt

class RelationshipClassification(BaseModel):
    relationship: str = Field(description="The classified relationship: supplier, customer, partner, competitor, subsidiary, or unknown")
    confidence: float = Field(description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Brief explanation for the classification")

def get_relationship_chain(provider="openai", model="gpt-4o"):
    llm = get_llm(provider=provider, model=model)
    parser = PydanticOutputParser(pydantic_object=RelationshipClassification)
    
    # We use a partial to inject format_instructions later or we can do it during invocation
    chain = relationship_prompt | llm | parser
    return chain
