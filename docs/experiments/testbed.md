# The Labyrinth testbed

A partially observable, non-stationary grid world, built so that each cognitive
pressure in the architecture has something real to push against. The environment
knows nothing about cognition: it declares tools, emits percepts, and advances its
own hidden dynamics.

## What each feature is for

| feature | pressure it creates |
|---|---|
| unknown map, revealed only adjacent | curiosity; knowledge gaps |
| locked passages needing coloured keys | dependency emergence via relaxed planning |
| scanner that is noisy and drifts with use | contradiction; source-reliability learning |
| a `calibrate` tool declaring `maintains="scan"` | hypothesis formation and testing |
| hazards that move every 30 ticks | risk; validation before committing |
| relics and oil that respawn | opportunity; non-stationarity |
| energy and integrity | maintain goals; resource trade-offs |
| the thread returns to the maze when deposited | persistence; a task that never ends |

## Capabilities declared

`move`, `take`, `unlock`, `deposit` (actions, with grounding, preconditions and
effects for the planner); `consume`, `rest`, `calibrate` (maintenance, declaring
what they restore or maintain); `scan`, `probe` (epistemic, declaring what they
reveal and how far they reach).

Note what is *not* declared: any statement that the thread matters more than
relics beyond its value, that keys should be fetched before doors are approached,
or that the scanner should be recalibrated when it drifts. Those are the behaviours
we want to see emerge, so they are absent from the capability layer.

## Difficulty

The generator builds a randomized spanning tree, then places the thread at the
deepest room behind a gold-locked passage, a silver-locked side chamber holding the
richest relic, and the keys out in the open maze. The minimum solution therefore
requires: explore → find the gold key → realize the vault is unreachable → fetch
the key → unlock → explore the vault → find the thread → carry it back. That chain
is four levels of goal dependency deep, and the agent must construct all of it.

## Writing another environment

Implement `Environment`: a `WorldSchema`, `capabilities()`, `sources()`,
`initial_goals()`, `sense()`, `execute()`, `advance()`, `traversal_blocked()`,
`ground_truth()`, `task_metrics()`, and optionally `layout()` for the console.

If anything in `core/`, `intentions/`, `goals/` or `cognition/` needs to change to
accommodate your environment, that is a bug in the separation and worth an issue.
