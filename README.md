# SocialMemBench

**A benchmark for evaluating AI memory systems in multi-party social group conversations.**

[![Code: MIT](https://img.shields.io/badge/Code-MIT-lightgrey.svg)](LICENSE) [![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](LICENSE-DATA)
[![Dataset: 1031 QA × 43 networks](https://img.shields.io/badge/QA-1%2C031%20across%2043%20networks-blue)](#dataset)
[![Quality: 0.952 blind-critic](https://img.shields.io/badge/blind--critic%20mean-0.952-green)](#dataset)

## What it measures

Memory systems for AI assistants were built for single-user dialogue and fail characteristically in multi-party social group settings. Existing benchmarks evaluate dyadic chat (LaMP, LoCoMo, MSC) or workplace dialogue (EverMemBench); none targets multi-party social groups, where memory must anchor facts in shared history rather than professional roles, separate group norms from individual exceptions, and correctly attribute even after member departure.

SocialMemBench evaluates the write-index-retrieve substrate between sessions across 43 ego networks, 1,031 QA pairs, and nine query categories. See the paper for evaluation results and architectural analysis.

## Dataset

- **43 ego networks** spanning 5 social-group types (close friends, family, recreational, interest community, acquaintance network)
- **1,031 QA pairs** across **9 query categories**
- **3 size tiers**: small (4–6 members), medium (8–10), large (15–30)
- **7,355 conversation turns** across **348 sessions**
- **430 personas** with structured profiles
- **Quality**: blind-critic mean **0.952**; every QA pair human-reviewed in the audit viewer

## Quick start

```python
from datasets import load_dataset

networks      = load_dataset("<org>/socialmembench", "networks",      split="train")
personas      = load_dataset("<org>/socialmembench", "personas",      split="train")
conversations = load_dataset("<org>/socialmembench", "conversations", split="train")
qa            = load_dataset("<org>/socialmembench", "qa",            split="train")
```

```bash
pip install -e .
python -m eval.cli --condition graphiti --network grp_a0b1c2d3
```

## Reproducing paper results

Every table, figure, and headline number in the paper is regenerated from
tracked data by:

```bash
make setup          # pip install -e .
make paper          # tables + figures + printed numbers (offline, no API keys)
```

Individual targets:

| Command | Regenerates |
|---|---|
| `make tables` | every CSV table under `data/results/tables/`, `data/results/category_counts.csv`, `data/results/bootstrap_cis.json`, `data/verify/sensitivity_threshold_table.*` |
| `make figures` | every PDF/PNG under `figures/` |
| `make paper-numbers` | stdout dump of every headline number cited in the paper |
| `make verify` | regenerates all of the above and diffs against tracked copies (exit 0 iff nothing drifted) |

Targets that require API keys and cost money are documented in the Makefile
under a separate section and are not part of `make paper`.

See `scripts/repro/README.md` for the underlying scripts and
`plans/repro-cleanup-plan.md` for the paper-artifact-to-script mapping.

## Query categories

| Code | Name | Tests |
|------|------|-------|
| SR | Single-contact recall | One person's implicit preference |
| GD | Group decision recall | Decision + dissenters |
| MA | Multi-contact aggregation | All members on one domain |
| AP | Attribution probe | Correct speaker when two are confusable |
| TM | Theory of mind | What A revealed about B's preference |
| NI | Norm vs. individual | Whether a group norm applies to everyone |
| RE | Relational edge | Relationship history revealed in chat |
| TS | Temporal shift | How a preference changed across sessions |
| DM | Departed member | Last known preference of a member who left |

## Methodology

Conversations are synthetically generated. The pipeline plants ground-truth challenges at known `(speaker, session, turn)` coordinates, enforces per-persona communication profiles, and controls implicitness levels. Generation specs are in `skills/`; validation runs through `smb-verify` (structural integrity) and `smb-qc` (blind-critic QA quality).

## Citation

```bibtex
@inproceedings{owolabi2027socialmembench,
  title     = {{SocialMemBench}: Are {AI} Memory Systems Ready for Social Group Settings?},
  author    = {Owolabi, Olukunle},
  booktitle = {Proceedings of the Conference of the European Chapter of the Association for Computational Linguistics (EACL)},
  year      = {2027}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable metadata.

## License

Code: [MIT](LICENSE). Data: [CC BY 4.0](LICENSE-DATA); attribution is the only requirement, and commercial and derivative use is permitted.
