from support_assistant.config import Settings
from support_assistant.adapters.embeddings.sentence_transformer import SentenceTransformerEmbedder
from support_assistant.rag.indexing import build_index
import json

if __name__ == "__main__":
    settings = Settings.from_env()
    embedder = SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_revision)
    print(json.dumps(build_index(settings, embedder), indent=2))
