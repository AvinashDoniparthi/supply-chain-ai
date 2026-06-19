from langchain_core.output_parsers import StrOutputParser
from providers.llm_provider import get_llm
from prompts.executive_report_prompt import executive_report_prompt

def get_executive_summary_chain(provider="openai", model="gpt-4o"):
    llm = get_llm(provider=provider, model=model)
    chain = executive_report_prompt | llm | StrOutputParser()
    return chain
