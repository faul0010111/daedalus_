# Memory

Five stores, each with a distinct job, plus a consolidation loop that turns
experience into something reusable.

| store | holds | bounded by |
|---|---|---|
| working | active short-term context | capacity, displacement |
| episodic | every action with reward, information gain, surprise | capacity, salience-based forgetting |
| semantic | consolidated statistics, lessons, source models, team outcomes | signature |
| strategic | per-variant performance and the full adaptation audit | — |
| failure | failures with context, diagnosed cause, recovery | capacity |

## Consolidation

Consolidation is not scheduled. The loop accumulates pressure as unconsolidated
episodes pile up and proposes a `CONSOLIDATE_MEMORY` intention that must win
attention like anything else — cheap, so it usually does, but it can be crowded
out when the agent is in trouble, which is the correct priority.

When it runs, episodes are grouped by signature (`intention_kind:tool`) and folded
into running statistics: success rate, mean reward, sample count. Those statistics
feed back as the `historical_success_rate` feature, closing the loop from
experience to attention.

Forgetting is salience-based: consolidated, unsurprising episodes are dropped
first. Surprising ones survive, because they are the ones reflection still has
work to do on.

## Retrieval

Episodes are indexed by a dependency-free hashing embedder over their natural
description, so `recall("take relic failed")` returns similar past experiences.
`Embedder` and `VectorIndex` are protocols — pgvector or Qdrant drop in without
touching the memory system.

## What memory is for

The test is whether the second thousand ticks are cheaper than the first. Source
models make the agent trust the right channel; failure lessons name the cause
(*"beliefs mostly came from 'scan'"*) rather than the symptom; strategic records
give the adaptation loop something to compare against; team outcomes record what a
particular organizational shape actually achieved.
