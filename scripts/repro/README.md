# scripts/repro/

Thin wrappers around the existing reproduction scripts. These give the reader
one canonical shell command per paper artifact, so that "how do I regenerate
Table 13?" has an answer you can copy-paste.

Every script in this directory is:

- Offline (no API calls, no network access).
- Idempotent (safe to re-run).
- Read-only against everything except its documented output paths.

Nothing here does anything the underlying script does not already do. The
value is in the discoverability and in the guarantee that the commands stay in
sync with the paper as the tree evolves.

## What each wrapper does

| Wrapper | Underlying script | Produces |
|---|---|---|
| `make_all_tables.sh` | bootstrap, ablation, category counts, category CIs, sensitivity | every CSV/TSV/TeX table cited in the paper |
| `make_figures.sh` | `figures/generate_figures.py` | every PDF/PNG figure |
| `print_paper_numbers.sh` | `scripts/print_paper_numbers.py`, `scripts/human_judge_agreement.py analyze` | stdout dump of every headline number, incl. App. C.4 agreement |
| `verify_reproduction.sh` | regenerates tables + figures, diffs against tracked copies | exit code 0 iff nothing drifted |
| `run_all_offline.sh` | everything above in the correct order | full offline reproduction from tracked data |

## When to use `make` vs these scripts

The top-level `Makefile` at the repo root calls into these wrappers. `make paper` runs `run_all_offline.sh` end-to-end. Use `make` when you want the standard flow; call these directly when you want more control or want to see the exact command being invoked.
