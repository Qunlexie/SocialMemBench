#!/usr/bin/env python3
"""
validate_croissant.py — validate hf_dataset/croissant.json against the MLCommons
Croissant spec via mlcroissant.

Requires Python 3.10+ (mlcroissant uses `X | Y` union syntax). On macOS, install
via:
    brew install python@3.11
    python3.11 -m pip install mlcroissant
    python3.11 scripts/validate_croissant.py

Usage:
    python3.11 scripts/validate_croissant.py
    python3.11 scripts/validate_croissant.py --file path/to/croissant.json

Exits 0 if no errors, 1 if errors are found. Warnings are reported but do not
fail the run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO_ROOT / "hf_dataset" / "croissant.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Validate Croissant metadata via mlcroissant.")
    p.add_argument("--file", type=Path, default=DEFAULT_FILE,
                   help=f"Croissant JSON-LD file to validate (default: {DEFAULT_FILE}).")
    args = p.parse_args()

    if not args.file.exists():
        print(f"FAIL: file not found: {args.file}")
        return 1

    if sys.version_info < (3, 10):
        print(f"FAIL: mlcroissant requires Python 3.10+. You have {sys.version_info.major}.{sys.version_info.minor}.")
        print("On macOS: brew install python@3.11 && python3.11 -m pip install mlcroissant")
        return 1

    try:
        from mlcroissant import Dataset
    except ImportError:
        print("FAIL: mlcroissant not installed. Run: python3.11 -m pip install mlcroissant")
        return 1

    print(f"Validating: {args.file}")
    ds = Dataset(jsonld=str(args.file))
    issues = ds.metadata.issues
    errors = list(issues.errors) if issues.errors else []
    warnings = list(issues.warnings) if issues.warnings else []

    print(f"  Name: {ds.metadata.name}")
    print(f"  Version: {ds.metadata.version}")
    print(f"  License: {ds.metadata.license}")
    print()
    print(f"Errors: {len(errors)}")
    for e in errors:
        print(f"  - {e}")
    print(f"Warnings: {len(warnings)}")
    for w in warnings:
        print(f"  - {w}")

    # NeurIPS croissant-rai-checker does literal key match (no JSON-LD expansion).
    # Keys must appear with explicit prefix as top-level JSON keys.
    required_keys = [
        "rai:dataLimitations",
        "rai:dataBiases",
        "rai:personalSensitiveInformation",
        "rai:dataUseCases",
        "rai:dataSocialImpact",
        "rai:hasSyntheticData",
        "prov:wasGeneratedBy",
    ]
    import json
    raw = json.loads(args.file.read_text())
    missing = [k for k in required_keys if k not in raw]
    if missing:
        print()
        print(f"NeurIPS RAI fields missing: {missing}")
        return 1

    if errors:
        print()
        print("Validation FAILED.")
        return 1

    print()
    print("Validation PASSED. Croissant is upload-ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
