import os
from langchain_openai import OpenAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

def get_embeddings(provider="openai"):
    if provider == "openai":
        return OpenAIEmbeddings(openai_api_key=os.environ.get("OPENAI_API_KEY") or "mock-key")
    elif provider in ["gemini", "google"]:
        return GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=os.environ.get("GOOGLE_API_KEY") or "mock-key")
    else:
        raise ValueError(f"Unknown embeddings provider: {provider}")

# For persistent storage
CHROMA_DB_DIR = "database/chroma_db"

def index_analysis(state, provider="openai"):
    """
    Indexes supplier profiles, risk assessments, and executive reports into Chroma.
    """
    embeddings = get_embeddings(provider)
    vector_store = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    
    documents = []
    
    # Supplier profiles
    if state.suppliers:
        for supplier in state.suppliers:
            content = f"Supplier: {supplier.name}\n"
            content += f"Evidence: {' '.join([e.get('snippet', '') for e in supplier.evidence])}"
            documents.append(Document(page_content=content, metadata={"type": "supplier", "name": supplier.name}))
        
    # Risk assessments
    if state.risk_assessments:
        for risk in state.risk_assessments:
            content = f"Risk for {risk.supplier_name}: {risk.risk_type}\n"
            content += f"Severity: {risk.severity}\n"
            content += f"Reasoning: {risk.reasoning}"
            documents.append(Document(page_content=content, metadata={"type": "risk", "supplier": risk.supplier_name}))
        
    # Executive report
    if hasattr(state, 'executive_report') and state.executive_report:
        report = state.executive_report
        content = f"Executive Report for {report.company_name}\n"
        content += f"Health Score: {report.overall_health_score}\n"
        content += f"Summary: {report.executive_summary}"
        documents.append(Document(page_content=content, metadata={"type": "executive_report", "company": report.company_name}))
        
    if documents:
        vector_store.add_documents(documents)
        print(f"Indexed {len(documents)} documents into Chroma vector store.")
    
    return vector_store

def search_analysis(query, provider="openai"):
    """
    Searches the analysis results in Chroma.
    """
    embeddings = get_embeddings(provider)
    vector_store = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    return vector_store.similarity_search(query)
