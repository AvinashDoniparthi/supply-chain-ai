from langchain_core.prompts import ChatPromptTemplate

relationship_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a supply chain intelligence analyst. Classify only from the evidence provided; do not infer relationships from generic industry co-occurrence."),
    ("user", """Analyze the relationship between the Target Company and the Candidate Entity using the supplied structured context and evidence snippets.

Target Company: {target_company}
Candidate Entity: {candidate_entity}

Evidence:
"{evidence}"

Classify the relationship into exactly one of these labels:
- supplier: Candidate supplies, manufactures for, is a foundry for, is a contract manufacturer for, provides components to, is a vendor to, or has a supply agreement with Target.
- upstream_supplier: Candidate supplies the Target's supplier, foundry, manufacturer, or another upstream parent in the supplied path.
- customer: Target supplies products or services to Candidate.
- partner: Target and Candidate collaborate, have a joint venture, or strategic partnership without clear supply direction.
- competitor: Target and Candidate compete in the same market.
- unrelated: Evidence does not establish a supply-chain relationship, or the entity is only a peer, investor, subsidiary, lawsuit counterparty, energy company, or generic co-mention.
- product_or_brand: Candidate is a product line, device, brand, model, technology, or category rather than a supplier company.

Negative evidence such as shareholder, investor, acquired, chairman, CEO, founder, peer, or generic "partnered with" should not be classified as supplier unless the evidence also contains explicit supplier language.
Return meaningful confidence: high only for direct supplier/customer/upstream-supplier statements, medium for multiple consistent snippets, and low for weak or ambiguous evidence.

{format_instructions}""")
])
