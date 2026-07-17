from __future__ import annotations

from typing import Literal

from llm.gemma_client import generate_with_gemma
from llm.gemini_client import generate_with_gemini

ModelMode = Literal["llm", "rag", "slm"]


def generate_response(
    prompt: str,
    mode: ModelMode,
    *,
    retrieved_context: str | None = None,
) -> str:
    """Route a prompt to the selected experimental mode."""

    if mode == "slm":
        return generate_with_gemma(prompt)

    if mode == "llm":
        return generate_with_gemini(prompt)

    if mode == "rag":
        if not retrieved_context:
            raise ValueError("RAG mode requires retrieved context.")

        grounded_prompt = f"""
        Use the retrieved evidence below to answer the request.

        RETRIEVED CONTEXT:
        {retrieved_context}

        USER REQUEST:
        {prompt}

        Do not introduce supplier relationships unsupported by the context.
        """

        return generate_with_gemini(grounded_prompt)

    raise ValueError(f"Unsupported model mode: {mode}")
