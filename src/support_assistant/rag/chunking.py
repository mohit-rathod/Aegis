from support_assistant.domain.evidence import Chunk


def chunk_documents(documents, embedder, size=160, overlap=24):
    if not 0 <= overlap < size:
        raise ValueError("Invalid overlap")
    chunks = []
    for doc in documents:
        # Leave room for document title, separator, and special tokens.
        title_tokens = len(embedder.spans(doc.title, 1, 0))
        if size + title_tokens + 8 > embedder.max_tokens:
            raise ValueError("Chunk plus title exceeds embedding model budget")
        for i, span in enumerate(embedder.spans(doc.body, size, overlap), 1):
            chunks.append(
                Chunk(
                    f"{doc.document_id}:{i:03}",
                    doc.document_id,
                    f"{doc.title}\n\n{span}",
                )
            )
    return chunks
