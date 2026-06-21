from langchain_core.output_parsers import StrOutputParser
from providers.llm_provider import get_llm, resolve_provider
from prompts.executive_report_prompt import executive_report_prompt

def get_executive_summary_chain(provider=None, model=None):
    config = resolve_provider(provider=provider, model=model)
    llm = get_llm(provider=config.provider, model=config.model)
    chain = executive_report_prompt | llm | StrOutputParser()
    return chain
