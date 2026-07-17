from __future__ import annotations

from typing import Any

import ollama

GEMMA_MODEL = "gemma3:4b"


def generate_with_gemma(
    prompt: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 1200,
) -> str:
    """Generate a response using the local Gemma model through Ollama."""

    if not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    try:
        response: Any = ollama.chat(
            model=GEMMA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a supply-chain intelligence assistant. "
                        "Follow the requested output format exactly. "
                        "Do not invent unsupported supplier relationships."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 4096,
            },
        )

        content = response["message"]["content"]

        if not content or not content.strip():
            raise RuntimeError("Gemma returned an empty response.")

        return content.strip()

    except Exception as exc:
        raise RuntimeError(
            "Gemma generation failed. Confirm that Ollama is running "
            "and that gemma3:4b is installed."
        ) from exc
