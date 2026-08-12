import ollama

EMBEDDING_MODEL = "nomic-embed-text"


def embed_text(text: str) -> list[float]:
    response = ollama.embed(model=EMBEDDING_MODEL, input=text)
    return response["embeddings"][0]
