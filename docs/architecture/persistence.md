# Persistence and state

DAEDALUS is stateful by design: an agent that forgets between runs cannot have a
memory that pays for itself. Persistence is a port so the reference stack stays
dependency-free while production stores drop in unchanged.

## Ports and adapters

| port | protocol | reference adapter | production options |
|---|---|---|---|
| snapshots and events | `core.state.StateStore` | `SQLiteStateStore` | PostgreSQL |
| episode similarity | `memory.embedding.VectorIndex` | `InMemoryVectorIndex` | pgvector, Qdrant |
| embeddings | `memory.embedding.Embedder` | `HashingEmbedder` | any model endpoint |
| transient state | in-process blackboard | — | Redis |
| goal and memory graphs | `GoalGraph`, `memory_graph()` | in-process | a graph layer |

## What a snapshot contains

Tick, RNG state, the full world model (beliefs with evidence and history,
contradictions, source posteriors, coverage, hypotheses), environment state, the
goal graph with its edges and transition history, autonomy counters, semantic
memory, adopted strategy variants and the learned attention bias.

That is enough to resume cognition, not merely to inspect it:
`test_state_snapshot_round_trips` restores a run into a fresh agent and continues
ticking it.

## What is deliberately not persisted

Live intentions and the current focus. An intention exists only while something
keeps proposing it, so after a restore the economy re-derives what matters from
the restored world model and goals. Persisting a focus would restore a decision
rather than the conditions that produced it — and the conditions are the state that
matters.

## Events

The bus keeps a bounded in-memory history for the console and appends to the store
on snapshot. Decision traces can additionally be streamed to JSONL by setting
`Tracer.jsonl_path`, which is the format to use for offline analysis of why a
particular intention won at a particular tick.
