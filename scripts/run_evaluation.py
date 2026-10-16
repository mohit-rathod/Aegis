import argparse
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from support_assistant.config import Settings
from support_assistant.bootstrap import build_retriever, build_service

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--answers", action="store_true", help="Also call Groq; otherwise retrieval-only")
    p.add_argument("--dataset", type=Path, default=Path("evaluation/datasets/aegis_grounding_seed.jsonl"))
    p.add_argument("--output", type=Path, default=Path("var/evaluation/aegis-results.json"))
    args = p.parse_args()
    settings = Settings.from_env()
    retriever = build_retriever(settings)
    service, llm = build_service(settings) if args.answers else (None, None)
    rows = []
    try:
        for line in args.dataset.read_text().splitlines():
            case = json.loads(line)
            start = time.monotonic()
            hits = retriever.retrieve(case["question"])
            ids = [h.document.document_id for h in hits]
            relevant = set(case["expected_document_ids"])
            rank = next((i for i,d in enumerate(ids,1) if d in relevant), None)
            row = {"id":case["id"], "retrieved":ids,
                "hit_at_k": bool(rank), "recall_at_k":len(set(ids)&relevant)/len(relevant),
                "reciprocal_rank":1/rank if rank else 0,
                "retrieval_ms":(time.monotonic()-start)*1000,
                "expected_behavior":case["expected_behavior"]}
            if service:
                start = time.monotonic()
                response = service.handle(case["question"])
                row["response"] = response.model_dump()
                row["response_ms"] = (time.monotonic()-start)*1000
                row["behavior_match"] = response.status == case["expected_behavior"]
                row["expected_answer_facts_for_manual_review"] = case["expected_answer_facts"]
            rows.append(row)
    finally:
        if llm: llm.close()
    if not rows: raise ValueError("Empty evaluation dataset")
    results = {"created_at":datetime.now(timezone.utc).isoformat(),
        "dataset":str(args.dataset), "split":"development_seed",
        "top_k_documents":settings.top_k_documents, "min_similarity":settings.min_similarity,
        "embedding_model":settings.embedding_model, "embedding_revision":settings.embedding_revision,
        "groq_model":settings.groq_model if args.answers else None,
        "index_metadata":retriever.index.metadata, "count":len(rows),
        "hit_at_k":sum(r["hit_at_k"] for r in rows)/len(rows),
        "recall_at_k":sum(r["recall_at_k"] for r in rows)/len(rows),
        "mrr_at_k":sum(r["reciprocal_rank"] for r in rows)/len(rows),
        "answer_factuality":"not automatically scored; manual evidence review required",
        "rows":rows}
    if args.answers:
        results["behavior_match_rate"] = sum(r["behavior_match"] for r in rows)/len(rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,indent=2)+"\n")
    print(f"Saved {len(rows)} cases to {args.output}")

if __name__ == "__main__": main()
