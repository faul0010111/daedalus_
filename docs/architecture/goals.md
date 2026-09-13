# Goal emergence and the dynamic goal graph

Goals are a graph, not a list. They emerge, split, merge, suspend, get abandoned
and reactivate, and each transition is recorded with its reason.

## Kinds

- `ACHIEVE` — make a fact true.
- `KNOW` — find a binding for a pattern containing variables (`?room contains thread`).
- `MAINTAIN` — keep a quantity above a threshold. Its urgency is a function of
  *state*, not of age: as energy approaches its floor, urgency rises continuously.

## Two mechanisms of emergence

Both reason over declared capabilities. Neither knows anything about labyrinths.

**Knowledge-gap regression.** Tools declare what they `produce`, what they
`require`, and what must be `known`. To make `thread deposited yes`, `deposit`
requires holding the thread; `take` produces holding but requires knowing
`?room contains thread`; that is unknown. The unknown is the gap, and it becomes a
`KNOW` subgoal.

**Relaxed planning.** The planner may violate preconditions marked `relaxable` at
a heavy penalty. When the goal is unreachable, the cheapest violating plan names
the blockers — `agent holding key:gold` — and each becomes an `ACHIEVE` subgoal.
The goal itself transitions to `blocked` with the dependency written into its
reason.

**Barriers.** When a `KNOW` goal exhausts the frontier it can walk to, the
unexplored region beyond a locked passage is a *dependency*, not an absence. The
goal engine computes what would be reachable if barriers were passable and spawns
a goal to get there — which then triggers relaxed planning, which finds the key,
which triggers gap analysis, which triggers exploration.

That chain is the clearest demonstration of the thesis in the repository, and no
step of it is scripted.

## Graph mechanics

- **Value propagates down.** A subgoal is worth at most what the parent it serves
  is worth, discounted per level; `test_subgoal_inherits_importance_from_what_it_serves`
  holds this invariant.
- **Deduplication over duplication.** A goal with an existing open signature is
  not recreated; the new parent is linked to the existing goal instead, which is
  how two goals come to share a dependency.
- **Cycles are refused** when linking.
- **Obsolescence, not failure.** An emergent goal whose parents have all closed is
  abandoned. A goal that merely keeps failing is *suspended* with periodic
  reconsideration — abandoning a goal its parent still needs only causes the graph
  to churn through identical replacements, which is a mistake this implementation
  made and now has a guard against.
- **Persistent goals reopen.** The thread slips back into the maze after being
  returned; the goal notices it no longer holds and reactivates. Nothing polls for
  this — the ordinary satisfaction check catches it.

## Satisfaction

Goals close when the *world model* says the condition holds, not when the
environment says so. An agent that has returned the thread but does not believe it
has, has not finished — and an agent convinced by a noisy sensor will close a goal
it should not have. Both are correct behaviours for a system whose beliefs are the
only thing it can act on.
