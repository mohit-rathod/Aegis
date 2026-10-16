import argparse
import json
from support_assistant.config import Settings

def main():
    parser = argparse.ArgumentParser(description="Aegis document-aware RAG")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-index")
    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("question")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "build-index":
            from support_assistant.adapters.embeddings.sentence_transformer import SentenceTransformerEmbedder
            from support_assistant.rag.indexing import build_index
            result = build_index(settings, SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_revision))
        elif args.command == "retrieve":
            from support_assistant.bootstrap import build_retriever
            result = [{"document_id": h.document.document_id, "title": h.document.title,
                "score": round(h.score, 4), "matched_chunks": h.matched_chunk_ids}
                for h in build_retriever(settings).retrieve(args.question)]
        else:
            import asyncio
            import uuid
            from support_assistant.bootstrap_part_a import create_runtime
            from support_assistant.domain.conversation import Turn
            from support_assistant.observability.logging import configure_logging
            configure_logging()
            async def ask_once():
                runtime = await create_runtime()
                try:
                    session = await runtime.store.create("customer-a")
                    response = await runtime.service.handle("customer-a", session.session_id,
                        Turn(turn_id=uuid.uuid4().hex, text=args.question))
                    return response.model_dump(mode="json")
                finally:
                    await runtime.aclose()
            result = asyncio.run(ask_once())
        print(json.dumps(result, indent=2))
    except Exception as exc:
        # CLI setup failures are explicit; no unvalidated answer is produced.
        parser.exit(1, f"Setup/execution error ({type(exc).__name__}). Check configuration, dependencies, manifest and index.\n")

if __name__ == "__main__":
    main()
