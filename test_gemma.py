from llm.gemma_client import generate_with_gemma


def main() -> None:
    prompt = """
    Identify the likely direct display-panel suppliers for Apple's iPhone.

    Return only valid JSON in this format:

    {
      "suppliers": [
        {
          "supplier_name": "string",
          "relationship": "string",
          "confidence": 0.0
        }
      ]
    }

    Do not include final-assembly companies.
    """

    response = generate_with_gemma(prompt)
    print(response)


if __name__ == "__main__":
    main()
