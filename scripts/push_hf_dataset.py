#!/usr/bin/env python3
"""
push_hf_dataset.py — push hf_dataset/ to the HuggingFace Hub.

Reads HF_TOKEN and HF_REPO_ID from .env. The repo ID is intentionally not
hardcoded so this script can be shared without leaking the submission
account name. Default mode prints what would be pushed; pass --write
to actually upload.

Typical workflow before pushing:
    python3 scripts/build_hf_dataset.py --write       # rebuild parquets
    python3 scripts/build_croissant.py --write        # rebuild Croissant
    python3 scripts/validate_hf_dataset.py            # sanity check
    python3 scripts/push_hf_dataset.py --write        # push

Usage:
    python3 scripts/push_hf_dataset.py                # dry run
    python3 scripts/push_hf_dataset.py --write
    python3 scripts/push_hf_dataset.py --write --repo-id ORG/socialmembench
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = REPO_ROOT / "hf_dataset"
DEFAULT_ENV = REPO_ROOT / ".env"
DEFAULT_COMMIT_MSG = "Update dataset"


def _load_env_var(env_path: Path, key: str) -> str:
    if not env_path.exists():
        raise SystemExit(f"No {env_path} found. Set {key} in .env.")
    prefix = f"{key}="
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'")
    raise SystemExit(f"{key} not found in {env_path}.")


def main() -> None:
    p = argparse.ArgumentParser(description="Push hf_dataset/ to the HuggingFace Hub.")
    p.add_argument("--folder", type=Path, default=DEFAULT_FOLDER,
                   help=f"Folder to upload (default: {DEFAULT_FOLDER}).")
    p.add_argument("--repo-id", default=None,
                   help="HF repo ID. Defaults to HF_REPO_ID in .env.")
    p.add_argument("--commit-message", default=DEFAULT_COMMIT_MSG,
                   help="Commit message for the upload.")
    p.add_argument("--env-file", type=Path, default=DEFAULT_ENV,
                   help=f"Path to .env with HF_TOKEN (default: {DEFAULT_ENV}).")
    p.add_argument("--write", action="store_true",
                   help="Actually push (default is dry-run).")
    args = p.parse_args()

    if not args.folder.is_dir():
        raise SystemExit(f"Folder not found: {args.folder}")

    repo_id = args.repo_id or _load_env_var(args.env_file, "HF_REPO_ID")
    files = sorted(f.relative_to(args.folder) for f in args.folder.rglob("*") if f.is_file())

    if not args.write:
        print(f"DRY RUN. Would upload {len(files)} file(s) from {args.folder} to {repo_id}:")
        for f in files:
            print(f"  {f}")
        print(f"\nCommit message: {args.commit_message!r}")
        print("Pass --write to actually push.")
        return

    from huggingface_hub import HfApi
    token = _load_env_var(args.env_file, "HF_TOKEN")
    print(f"Uploading {len(files)} file(s) from {args.folder} to {repo_id} ...")
    res = HfApi().upload_folder(
        folder_path=str(args.folder),
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=args.commit_message,
    )
    print(f"Uploaded. Commit URL: {res}")


if __name__ == "__main__":
    main()
