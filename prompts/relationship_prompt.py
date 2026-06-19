from langchain_core.prompts import ChatPromptTemplate

relationship_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a supply chain intelligence analyst."),
    ("user", """Analyze the relationship between the Target Company and the Candidate Entity based on the provided evidence snippet.

Target Company: {target_company}
Candidate Entity: {candidate_entity}

Evidence:
"{evidence}"

Classify the relationship into exactly one of these labels:
- supplier: Candidate supplies products or services to Target.
- customer: Target supplies products or services to Candidate.
- partner: Target and Candidate collaborate or have a joint venture.
- competitor: Target and Candidate compete in the same market.
- subsidiary: Candidate is owned by Target or is a division of Target.
- unknown: Relationship is unclear or not mentioned.

{format_instructions}""")
])
