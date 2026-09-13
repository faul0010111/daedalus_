# Architecture overview

DAEDALUS is built around one inversion: the runtime does not know what the agent
should think about. It knows how to let processes propose, how to run a
competition, and how to execute a single step of whatever won.

## The tick

`core/runtime/engine.py` is deliberately the shortest interesting file in the
repository. One tick is:

1. **Environment dynamics** advance (hidden from the agent; emitted as events for
   observability only).
2. **Perception** senses, compares against the previous percept, and writes into
   the world model. Coverage is applied: anything examined and not reported is
   evidence of absence.
3. **Due processes run.** Each `CognitiveProcess` has a `period` and a `phase`, so
   processes with the same cadence spread across ticks instead of stampeding.
   Every process either updates shared state or proposes intentions. None calls
   another.
4. **Stale intentions expire.** An intention survives only while something keeps
   proposing it — except the current focus, which is protected.
5. **Attention allocates.** One focal intention, plus up to one background slot
   for a cheap internal operation.
6. **The focal intention takes exactly one step** — one tool call, or one internal
   cognitive operation.
7. **Evaluation** turns the outcome into an episode with reward, information gain
   and surprise; drives are recomputed; metrics sample.

Note what is absent: no stage decides the next stage. The sequence above is the
*substrate's* order of operations, not the agent's reasoning.

## Layers

| layer | package | responsibility |
|---|---|---|
| substrate | `core/` | clock, event bus, runtime, configuration, persistence ports |
| epistemics | `world/` | beliefs, confidence, contradictions, hypotheses, source reliability |
| motivation | `intentions/`, `goals/` | proposal, scoring, attention, the dynamic goal graph |
| cognition | `cognition/` | perception, planning, reasoning, deliberation, reflection, adaptation |
| organization | `agents/` | temporary cognitive units and their lifecycle |
| memory | `memory/` | working, episodic, semantic, strategic, failure |
| capability | `tools/` | registry, execution, outcome evaluation |
| self-model | `meta/` | performance monitor, diagnostics, strategy evolution |
| observability | `observability/` | traces, metrics, graph projections, timelines |
| environment | `experiments/simulations/` | the port, and the Labyrinth testbed |

## Events

Everything cognitively meaningful is an event: belief revisions, contradictions,
proposals, attention allocations, preemptions, plans, actions, outcomes,
reflections, diagnoses, adaptations, agent spawns and dissolutions. The bus is
synchronous and deterministic so that experiments replay identically;
asynchronous consumers (the console's WebSocket) attach bounded queues and are
dropped from rather than allowed to block cognition.

## Determinism

Runs are reproducible for a fixed seed, and this is not incidental — it is what
makes ablations meaningful. Python randomizes string hashing per process, so any
`set` iteration that reaches a decision would silently decorrelate runs across
machines. Every such iteration is sorted. `test_runs_are_reproducible_for_a_fixed_seed`
fingerprints two full runs and compares them.

## The environment port

An environment declares:

- a `WorldSchema` — which predicates are functional, volatile, epistemic, fluent;
- `capabilities()` — `ToolSpec`s with grounding, preconditions, effects and costs;
- `sources()` — observation channels and the reliability they *claim*;
- `initial_goals()` — what the developer cares about;
- `sense()`, `execute()`, `advance()`, `ground_truth()`, `task_metrics()`.

Nothing else in the system is environment-aware. The planner, the gap analysis and
the frontier logic operate on the schema, not on the Labyrinth.

## Persistence

`StateStore` is a protocol; `SQLiteStateStore` is the reference adapter. Snapshots
capture the tick, RNG state, world model, environment, goal graph, metrics,
semantic memory, adopted strategies and the learned policy — enough to resume.
`test_state_snapshot_round_trips` restores a run and continues it.
