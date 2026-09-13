# Autonomy metrics

Eight experimental metrics, what each measures, and — more usefully — how each can
be inflated without any corresponding intelligence. Every one of these failure
modes was observed in an actual ablation run, not imagined.

| metric | definition |
|---|---|
| `self_initiated_actions` | actions serving intentions not proposed by the goal engine for a developer-given goal |
| `emergent_goals` | goals created by the system rather than declared by the developer |
| `knowledge_gaps_resolved` | `KNOW` goals closed by the agent finding the binding |
| `strategy_adaptations` | decision-point variants adopted after a trial |
| `agent_topology_changes` | temporary units spawned or dissolved |
| `reflection_events` | reflection loops executed |
| `uncertainty_reduction` | cumulative belief-entropy removed |
| `goal_progress_rate` | goals achieved per 100 ticks |

## How each is gamed

**`reflection_events`** — the worst offender. `fixed_pipeline` scores **798** and
achieves nothing, because its reflection is scheduled rather than earned;
`random_attention` scores 350 because cheap internal intentions win often under
uniform selection. The full architecture scores 48 and outperforms both by a factor
of ten in task value. *More
reflection is not more thought.*

**`agent_topology_changes`** — `no_curiosity` scores **146.6**, well above the full
architecture's 61.1, while returning almost nothing. With no exploration the agent's
goals stall permanently, stalling raises complexity pressure, and teams form and
dissolve in a loop. High churn reads as adaptability and means paralysis.

**`uncertainty_reduction`** — an agent that scans the same room forever accumulates
entropy reduction indefinitely, because volatile beliefs decay back and can be
re-reduced. It rewards busywork with a sensor.

**`self_initiated_actions`** — depends entirely on where you draw "initiated by the
developer". Our definition credits any action serving an emergent goal, so an agent
that spawns many shallow subgoals scores well for doing so.

**`emergent_goals`** — inflatable by generating duplicates. Deduplication by
signature is what keeps this honest here, and it is a property of the
implementation rather than of the metric.

**`strategy_adaptations`** — a loose adoption criterion inflates this directly. An
earlier version of our adaptation loop adopted several variants per run and made
behaviour *worse*; the current criterion adopts 0.8 per run. The count went down as
the mechanism got better.

## What to do instead

Read them as diagnostics against task outcome, never as an objective. The
comparison that carries information is *the same metric across architectures*:
`fixed_pipeline` scoring 798 reflections and 0.0 value is a far stronger result than
any absolute number.

If we had to pick two that resist gaming best: `knowledge_gaps_resolved`, because it
requires the agent to have both identified something it did not know and then found
it, and `goal_progress_rate` on goals it did not set itself.
