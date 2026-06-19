from langchain_core.prompts import ChatPromptTemplate

executive_report_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an executive business analyst writing supply chain intelligence reports."),
    ("user", """Generate a concise, professional executive summary for a company's supply chain analysis report based on the following data:

Overall Health Score: {health_score}
Key Suppliers: {suppliers}
Major Risks: {risks}

Provide a coherent paragraph summarizing the current supply chain status, principal risks, reliance on critical suppliers, and high-level recommendations or outlook.""")
])
