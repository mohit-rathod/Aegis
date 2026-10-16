import argparse
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("trace", type=Path)
    args = p.parse_args()
    groups = {}
    for line in args.trace.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") == "voice_latency":
            groups.setdefault(row["metric"], []).append(row["value"])
    for name, values in groups.items():
        print(
            json.dumps(
                {
                    "metric": name,
                    "samples": len(values),
                    "p50_ms": round(float(np.percentile(values, 50)), 2),
                    "p95_ms": round(float(np.percentile(values, 95)), 2),
                }
            )
        )
    if not groups:
        print("No completed voice latency samples in this trace.")


if __name__ == "__main__":
    main()
