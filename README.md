# SocialMemBench

**A benchmark for evaluating AI memory architectures in multi-party social group conversations.**

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![Dataset: 1031 QA × 43 networks](https://img.shields.io/badge/QA-1%2C031%20across%2043%20networks-blue)](#dataset)
[![Quality: 0.952 blind-critic](https://img.shields.io/badge/blind--critic%20mean-0.952-green)](#dataset)

## What it measures

Memory systems for AI assistants were built for single-user dialogue and fail characteristically in multi-party social group settings. Existing benchmarks evaluate dyadic chat (LaMP, LoCoMo, MSC) or workplace dialogue (EverMemBench); none targets multi-party social groups, where memory must anchor facts in shared history rather than professional roles, separate group norms from individual exceptions, and correctly attribute even after member departure.

SocialMemBench evaluates the write-index-retrieve substrate between sessions across 43 ego networks, 1,031 QA pairs, and nine query categories. Architectural failure modes and the named primitives that fix them are documented in the paper.

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

networks      = load_dataset("SocialMemBench", "networks",      split="data")
personas      = load_dataset("SocialMemBench", "personas",      split="data")
conversations = load_dataset("SocialMemBench", "conversations", split="data")
qa            = load_dataset("SocialMemBench", "qa",            split="data")
```

```bash
pip install -e .
python -m eval.cli --condition graphiti --network grp_a0b1c2d3
```

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
@misc{socialmembench2026,
  title  = {SocialMemBench: Evaluating AI Memory Architectures in Social Group Conversations},
  author = {Anonymous},
  year   = {2026}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable metadata.

## License

[CC BY 4.0](LICENSE). Attribution is the only requirement; commercial and derivative use is permitted.
