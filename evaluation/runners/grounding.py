import argparse
import asyncio
import json
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from support_assistant.bootstrap import build_retriever, create_runtime
from support_assistant.config import Settings
from support_assistant.domain.conversation import Turn


async def run(args):
    settings = Settings.from_env()
    prefix = settings.prefix + ":grounding-eval:" + uuid.uuid4().hex
    runtime = (
        await create_runtime(replace(settings, prefix=prefix)) if args.answers else None
    )
    retriever = (
        runtime.retriever
        if runtime
        else await asyncio.to_thread(build_retriever, settings)
    )
    rows = []
    try:
        for line in args.dataset.read_text().splitlines():
            case = json.loads(line)
            start = time.monotonic()
            hits = await asyncio.to_thread(retriever.retrieve, case["question"])
            ids = [h.document.document_id for h in hits]
            relevant = set(case["expected_document_ids"])
            rank = next((i for i, d in enumerate(ids, 1) if d in relevant), None)
            row = {
                "id": case["id"],
                "retrieved": ids,
                "hit_at_k": bool(rank),
                "recall_at_k": len(set(ids) & relevant) / len(relevant),
                "reciprocal_rank": 1 / rank if rank else 0,
                "retrieval_ms": (time.monotonic() - start) * 1000,
                "expected_behavior": case["expected_behavior"],
            }
            if runtime:
                # Fresh session per case prevents terminal/clarification state contamination.
                session = await runtime.store.create("customer-a")
                start = time.monotonic()
                response = await runtime.service.handle(
                    "customer-a",
                    session.session_id,
                    Turn(turn_id=uuid.uuid4().hex, text=case["question"]),
                )
                row["response"] = response.model_dump(mode="json")
                row["response_ms"] = (time.monotonic() - start) * 1000
                row["expected_answer_facts_for_review"] = case["expected_answer_facts"]
            rows.append(row)
    finally:
        if runtime:
            try:
                keys = [
                    key async for key in runtime.redis.scan_iter(match=prefix + ":*")
                ]
                for offset in range(0, len(keys), 500):
                    await runtime.redis.delete(*keys[offset : offset + 500])
            finally:
                await runtime.aclose()
    if not rows:
        raise ValueError("Empty evaluation dataset")
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "split": "development_seed",
        "mode": "live_support_system" if args.answers else "retrieval_only",
        "count": len(rows),
        "model": settings.embedding_model,
        "revision": settings.embedding_revision,
        "index_metadata": retriever.index.metadata,
        "top_k_documents": settings.top_k_documents,
        "min_similarity": settings.min_similarity,
        "hit_at_k": sum(r["hit_at_k"] for r in rows) / len(rows),
        "recall_at_k": sum(r["recall_at_k"] for r in rows) / len(rows),
        "mrr_at_k": sum(r["reciprocal_rank"] for r in rows) / len(rows),
        "answer_factuality": "manual evidence review required; status alone is not a correctness score",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Saved {len(rows)} cases to {args.output}")


def main():
    p = argparse.ArgumentParser(
        description="Evaluate retrieval and optional full support answers"
    )
    p.add_argument(
        "--answers",
        action="store_true",
        help="Also call the shared support service with live Groq",
    )
    p.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/datasets/aegis_grounding_seed.jsonl"),
    )
    p.add_argument(
        "--output", type=Path, default=Path("var/evaluation/retrieval-results.json")
    )
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
