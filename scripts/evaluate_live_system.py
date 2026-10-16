"""One explicit live evaluation command; never manufactures scores without Groq."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.runners.grounding import run as evaluate_retrieval
from evaluation.runners.support import run as evaluate_support


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {
        "mode": "live_groq",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": "development_seed_not_held_out",
        "status": "incomplete",
        "errors": [],
    }
    try:
        result = await evaluate_support(
            argparse.Namespace(suite="all", output=args.output / "support.json")
        )
        summary["model"] = result["model"]
        summary["suites"] = {
            name: {"count": suite["count"], "metrics": suite["metrics"]}
            for name, suite in result["suites"].items()
        }
        summary["errors"] = list(result["errors"])
        for name, suite in result["suites"].items():
            if suite["metrics"].get("provider_errors", 0):
                summary["errors"].append(
                    {
                        "suite": name,
                        "category": "provider_errors",
                        "count": suite["metrics"]["provider_errors"],
                    }
                )
        if args.retrieval:
            await evaluate_retrieval(
                argparse.Namespace(
                    answers=args.answers,
                    dataset=ROOT / "evaluation/datasets/aegis_grounding_seed.jsonl",
                    output=args.output / "retrieval.json",
                )
            )
        summary["status"] = "complete" if not summary["errors"] else "incomplete"
    except Exception as exc:
        summary["errors"].append(
            {
                "category": type(exc).__name__,
                "message": "Check credentials, Redis, index and provider availability. No result was invented.",
            }
        )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Live evaluation results",
        "",
        f"Status: {summary['status']}",
        "",
        "These are development-set measurements, not independent held-out guarantees. Provider errors are counted separately from semantic safety recall.",
        "",
    ]
    for name, suite in summary.get("suites", {}).items():
        lines += [
            "## " + name,
            "",
            "```json",
            json.dumps(suite["metrics"], indent=2),
            "```",
            "",
        ]
    if summary["errors"]:
        lines += ["Errors: " + json.dumps(summary["errors"])]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))
    if summary["status"] != "complete":
        raise SystemExit(2)


def main():
    p = argparse.ArgumentParser(
        description="Run actual Groq routing, safety and classifier-cache measurements"
    )
    p.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Explicitly consume real Groq quota",
    )
    p.add_argument(
        "--retrieval",
        action="store_true",
        help="Also evaluate embedding retrieval; needs the index",
    )
    p.add_argument(
        "--answers",
        action="store_true",
        help="With --retrieval, also generate full guarded answers",
    )
    p.add_argument("--output", type=Path, default=Path("var/evaluation/live-system"))
    args = p.parse_args()
    if args.answers and not args.retrieval:
        p.error("--answers requires --retrieval")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
