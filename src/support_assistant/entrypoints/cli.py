import argparse
import asyncio
import json
import uuid

from support_assistant.config import Settings
from support_assistant.observability.logging import configure_logging


async def run_support(args, settings):
    from support_assistant.bootstrap import create_runtime
    from support_assistant.domain.conversation import Turn

    runtime = await create_runtime(settings)
    try:
        session = await runtime.store.create(args.customer)
        if args.command == "ask":
            response = await runtime.service.handle(
                args.customer,
                session.session_id,
                Turn(turn_id=uuid.uuid4().hex, text=args.question),
            )
            print(json.dumps(response.model_dump(mode="json"), indent=2))
            return
        print(f"Aegis session: {session.session_id}")
        while True:
            try:
                text = await asyncio.to_thread(input, "You: ")
            except EOFError:
                break
            if text.strip().lower() in ["/quit", "/exit"]:
                break
            if len(text) > 2000:
                print(
                    "Assistant: Your message is too long. Please shorten it and try again."
                )
                continue
            response = await runtime.service.handle(
                args.customer,
                session.session_id,
                Turn(turn_id=uuid.uuid4().hex, text=text),
            )
            print("Assistant:", response.answer)
            if response.session_state == "terminated":
                break
    finally:
        await runtime.aclose()


async def show_metrics(settings):
    from redis.asyncio import Redis

    from support_assistant.adapters.cache.redis_cache import RedisClassifierCache

    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )
    try:
        metrics = await RedisClassifierCache(redis, settings.prefix).metrics()
        print(json.dumps(metrics, indent=2))
    finally:
        await redis.aclose()


def main():
    parser = argparse.ArgumentParser(description="Aegis Support Assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="Start a support conversation")
    ask = sub.add_parser("ask", help="Ask one question in a new session")
    for command in [chat, ask]:
        command.add_argument(
            "--customer",
            choices=["customer-a", "customer-b"],
            default="customer-a",
            help="Trusted local demo identity, not production authentication",
        )
    ask.add_argument("question")
    sub.add_parser("metrics", help="Show classifier cache metrics")
    sub.add_parser("build-index", help="Build the knowledge-base embedding index")
    retrieve = sub.add_parser("retrieve", help="Inspect retrieval for development")
    retrieve.add_argument("question")
    for name in ["serve", "voice"]:
        web = sub.add_parser(name, help="Start the text and voice support frontend")
        web.add_argument("--host", default="127.0.0.1")
        web.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    configure_logging()
    try:
        settings = Settings.from_env()
        if args.command in ["serve", "voice"]:
            import uvicorn

            uvicorn.run(
                "support_assistant.entrypoints.api.app:app",
                host=args.host,
                port=args.port,
                ws_max_size=16384,
                ws_max_queue=16,
            )
        elif args.command == "build-index":
            from support_assistant.adapters.embeddings.sentence_transformer import (
                SentenceTransformerEmbedder,
            )
            from support_assistant.rag.indexing import build_index

            result = build_index(
                settings,
                SentenceTransformerEmbedder(
                    settings.embedding_model, settings.embedding_revision
                ),
            )
            print(json.dumps(result, indent=2))
        elif args.command == "retrieve":
            from support_assistant.bootstrap import build_retriever

            hits = build_retriever(settings).retrieve(args.question)
            print(
                json.dumps(
                    [
                        {
                            "document_id": h.document.document_id,
                            "title": h.document.title,
                            "score": round(h.score, 4),
                            "matched_chunks": h.matched_chunk_ids,
                        }
                        for h in hits
                    ],
                    indent=2,
                )
            )
        elif args.command == "metrics":
            asyncio.run(show_metrics(settings))
        else:
            asyncio.run(run_support(args, settings))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        parser.exit(
            1,
            f"Execution error ({type(exc).__name__}). Check configuration, Redis, model access and index.\n",
        )


if __name__ == "__main__":
    main()
