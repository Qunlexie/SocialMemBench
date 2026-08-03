"""
Count QA pairs per query category from the released QA files and write the
per-category count table (paper Table 6).

Source:  data/qa/*.jsonl   (one record per QA pair, with a `query_type` field)
Output:  data/results/category_counts.csv   (query_type, n)

Pure aggregation; no API calls.
"""
import csv
import glob
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA_GLOB = os.path.join(ROOT, "data", "qa", "*.jsonl")
OUT = os.path.join(ROOT, "data", "results", "category_counts.csv")


def main():
    counts = Counter()
    for f in sorted(glob.glob(QA_GLOB)):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            qt = r.get("query_type")
            if qt:
                counts[qt] += 1
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["query_type", "n"])
        for qt in sorted(counts):
            w.writerow([qt, counts[qt]])
    print(f"wrote {os.path.relpath(OUT, ROOT)}  "
          f"({sum(counts.values())} QA pairs across {len(counts)} categories)")


if __name__ == "__main__":
    main()
