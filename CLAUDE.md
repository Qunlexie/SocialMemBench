# SocialMemBench — Claude Code Workflow

Data generation runs through Claude Code skill files. No API key needed — Claude Code IS the model.

## Pipeline (one network at a time)

```
/smb-generate-network {group_type} {group_size}
/smb-verify {network_id} --stage 1
/smb-generate-conversations {network_id} 5
/smb-verify {network_id} --stage 2
/smb-generate-qa {network_id}
/smb-qc {network_id}
/smb-verify {network_id} --stage 3
/smb-status
```

## Skills

| Command | Does |
|---------|------|
| `/smb-generate-network recreational 3` | Stage 1: generates ego network → `data/raw/{id}.json` |
| `/smb-generate-conversations {id} 5` | Stage 2: generates WhatsApp-style conversations → `data/conversations/{id}.json` |
| `/smb-generate-qa {id}` | Stage 3: generates Q1–Q8 QA pairs → `data/qa/{id}.jsonl` |
| `/smb-generate-qa {id} Q4 Q5` | Stage 3: only generate Q4 and Q5 for targeted coverage |
| `/smb-verify {id}` | Verify all 3 stages → `data/verify/{id}.json` |
| `/smb-verify {id} --stage 1` | Verify only Stage 1 (network quality) |
| `/smb-qc {id}` | Blind-critic QC on QA pairs → `data/qa/{id}_qc.json` |
| `/smb-status` | Show manifest + progress toward targets |
| `/smb-status {id}` | Drill into one network |

## Group types
`close_friends` · `family` · `recreational` · `interest_community` · `acquaintance_network`

## Data layout
```
data/
├── manifest.json              # incremental tracking — DO NOT edit manually
├── raw/{network_id}.json      # Stage 1: EgoNetwork
├── conversations/{network_id}.json   # Stage 2: ConversationCorpus
├── qa/{network_id}.jsonl      # Stage 3: QA pairs (append-only)
├── qa/{network_id}_qc.json    # QC report
└── verify/{network_id}.json   # Verification report
```

## Schemas (for reference)
- `socialmembench/schemas/persona.py` — EgoNetwork, Persona, RelationshipEdge, GroupNorm
- `socialmembench/schemas/conversation.py` — ConversationCorpus, ConversationTurn, PlantedChallenge
- `socialmembench/schemas/qa.py` — QAPair, EvidenceAnchor (Q1–Q8)

## Metrics
```bash
python -m socialmembench.utils.metrics --data_dir data/
```

## First run target: 50 QA pairs (manually verified before scaling to 1,000)
