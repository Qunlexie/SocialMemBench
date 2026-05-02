# Dataset Status

Show the current state of the SocialMemBench dataset: manifest summary, per-network status, and quality metrics.

## Arguments
None (or optional `$ARGUMENTS` for a specific network_id to drill into)

## Steps

### 1. Read `data/manifest.json`

If no network_id argument, show the full manifest summary:

```
=== SocialMemBench Dataset Status ===

Total QA pairs: {qa_pairs_total}
Total networks: {len(networks)}
  - complete:    {count}
  - verified:    {count}
  - stage2_done: {count}
  - stage1_done: {count}
  - pending:     {count}

Query type distribution:
  Q1 (single_contact_recall):       {count}
  Q2 (group_decision_recall):       {count}
  Q3 (multi_contact_aggregation):   {count}
  Q4 (contamination_probe):         {count}
  Q5 (theory_of_mind_reference):    {count}
  Q6 (norm_vs_individual):          {count}
  Q7 (relational_edge_query):       {count}
  Q8 (temporal_preference_evolution): {count}

Group type distribution:
  close_friends:        {count} networks
  family:               {count} networks
  recreational:         {count} networks
  interest_community:   {count} networks
  acquaintance_network: {count} networks

Most needed group type:  {type with lowest count}
Most needed query types: {top 3 with lowest counts}

Next seed: {next_seed}
```

Then list each network:
```
Networks:
  {network_id} | {group_name} | {group_type} | size={group_size} | status={status} | sessions={n_sessions} | qa={n_qa}
```

### 2. If a specific network_id is given

Show the drill-down:
```
Network: {network_id}
  Group: {group_name} ({group_type}, size {group_size})
  Status: {status}
  Seed: {seed}
  Sessions: {n_sessions}
  QA pairs: {n_qa}
  Consumed challenges: {len(consumed_challenge_ids)}

Files:
  data/raw/{network_id}.json     [{exists/missing}]
  data/conversations/{network_id}.json  [{exists/missing}]
  data/qa/{network_id}.jsonl    [{exists/missing}, {n} lines]
  data/verify/{network_id}.json [{exists/missing}]
  data/qa/{network_id}_qc.json  [{exists/missing}]
```

If `data/verify/{network_id}.json` exists, show the pass/fail summary.
If `data/qa/{network_id}_qc.json` exists, show the QC scores.

### 3. Progress toward targets

```
Progress toward 50 QA pairs (initial target):
  {qa_pairs_total}/50 ({pct}%)

Query type coverage (need ≥5 of each for initial target):
  Q1: {count}/5 {bar}
  Q2: {count}/5 {bar}
  Q3: {count}/5 {bar}
  Q4: {count}/5 {bar}
  Q5: {count}/5 {bar}
  Q6: {count}/5 {bar}
  Q7: {count}/5 {bar}
  Q8: {count}/5 {bar}
```

### 4. Suggested next steps

Based on manifest state, suggest what to run next:
- If any network is `stage1_done` with no conversations → suggest `/smb-generate-conversations {id} 5`
- If any network is `stage2_done` with no QA → suggest `/smb-generate-qa {id}`
- If QA pairs exist with no QC → suggest `/smb-qc {id}`
- If most-needed query types are Q4/Q5 → suggest `/smb-generate-qa {id} Q4 Q5`
- If qa_pairs_total < 50 → suggest generating the next group type
