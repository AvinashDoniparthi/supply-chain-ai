import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

def get_llm(provider: str = "openai", **kwargs):
    """
    Centralized provider factory for LangChain chat models.
    Supports 'openai' and 'gemini'.
    """
    provider = provider.lower()
    if provider == "openai":
        model_name = kwargs.get("model", "gpt-4o")
        if "model" in kwargs:
            kwargs.pop("model")
        
        api_key = kwargs.get("api_key") or kwargs.get("openai_api_key") or os.environ.get("OPENAI_API_KEY") or "mock-openai-key"
        if "api_key" in kwargs:
            kwargs.pop("api_key")
        if "openai_api_key" in kwargs:
            kwargs.pop("openai_api_key")
            
        return ChatOpenAI(model=model_name, openai_api_key=api_key, **kwargs)
        
    elif provider in ["gemini", "google"]:
        model_name = kwargs.get("model", "gemini-1.5-pro")
        if "model" in kwargs:
            kwargs.pop("model")
            
        api_key = kwargs.get("api_key") or kwargs.get("google_api_key") or os.environ.get("GOOGLE_API_KEY") or "mock-google-key"
        if "api_key" in kwargs:
            kwargs.pop("api_key")
        if "google_api_key" in kwargs:
            kwargs.pop("google_api_key")
            
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, **kwargs)
        
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
