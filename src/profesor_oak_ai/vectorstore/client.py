from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

QDRANT_PATH = Path(__file__).resolve().parents[3] / "data" / "qdrant"
COLLECTION_NAME = "pokedex_lore"

# nomic-embed-text's actual output dimension, confirmed empirically (not assumed):
# ollama.embed(model="nomic-embed-text", input=...)["embeddings"][0] has length 768.
EMBEDDING_DIM = 768


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(path=str(QDRANT_PATH))


def ensure_collection(client: QdrantClient) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
