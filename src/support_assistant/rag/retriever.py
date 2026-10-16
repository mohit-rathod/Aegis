from support_assistant.domain.evidence import Hit
from support_assistant.rag.documents import corpus_fingerprint

class Retriever:
    def __init__(self, index, documents, embedder, settings):
        expected = {
            "schema_version": 1,
            "corpus_fingerprint": corpus_fingerprint(documents),
            "embedding_model": embedder.model_id,
            "embedding_revision": embedder.revision,
            "embedding_dimension": index.vectors.shape[1],
            "chunk_tokens": settings.chunk_tokens,
            "chunk_overlap": settings.chunk_overlap,
        }
        for key, value in expected.items():
            if index.metadata.get(key) != value:
                raise ValueError(f"Stale or incompatible index ({key}); rebuild it")
        self.index, self.embedder, self.settings = index, embedder, settings
        self.documents = {d.document_id: d for d in documents}
        if any(c.document_id not in self.documents for c in index.chunks):
            raise ValueError("Index refers to an unknown source document")

    def retrieve(self, query):
        if not query.strip():
            raise ValueError("Question cannot be empty")
        ranked = self.index.ranked_chunks(self.embedder.encode([query])[0])
        scores, matched = {}, {}
        for chunk, score in ranked:
            if score < self.settings.min_similarity:
                continue
            scores.setdefault(chunk.document_id, score)
            matched.setdefault(chunk.document_id, []).append(chunk.chunk_id)
        chosen = sorted(scores, key=lambda doc_id: -scores[doc_id])[:self.settings.top_k_documents]
        # Expand each matched child into its full parent policy document.
        return [Hit(self.documents[d], scores[d], tuple(matched[d])) for d in chosen]
