import asyncio
from services.llm_extractor import LLMExtractor

async def test_extraction():
    prompt = "faire un devis sur la fourniture de 500 ref A00001 pour le client Edge Communications"
    result = await LLMExtractor.extract_quote_info(prompt)
    print("Résultat de l'extraction:", result)

if __name__ == "__main__":
    asyncio.run(test_extraction())