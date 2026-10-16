import importlib.metadata
from datetime import datetime, timezone

from support_assistant.adapters.retrieval.numpy_index import NumpyIndex
from support_assistant.rag.chunking import chunk_documents
from support_assistant.rag.documents import corpus_fingerprint, load_documents


def build_index(settings, embedder):
    documents = load_documents(settings.kb_dir)
    chunks = chunk_documents(
        documents, embedder, settings.chunk_tokens, settings.chunk_overlap
    )
    vectors = embedder.encode([c.text for c in chunks])
    try:
        library_version = importlib.metadata.version("sentence-transformers")
    except importlib.metadata.PackageNotFoundError:
        library_version = "test-embedder"
    metadata = {
        "schema_version": 1,
        "corpus_fingerprint": corpus_fingerprint(documents),
        "embedding_model": embedder.model_id,
        "embedding_revision": embedder.revision,
        "embedding_dimension": int(vectors.shape[1]),
        "sentence_transformers_version": library_version,
        "chunk_tokens": settings.chunk_tokens,
        "chunk_overlap": settings.chunk_overlap,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "chunk_count": len(chunks),
    }
    index = NumpyIndex(vectors, chunks, metadata)
    index.save(settings.index_dir)
    return metadata
