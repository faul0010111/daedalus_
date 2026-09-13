# Self-organization

There is no permanent planner, researcher, critic or executor. There are
*temporary cognitive units*, formed when a goal becomes complex enough to warrant
specialization and dissolved when it does not.

## Complexity pressure

Measured per root goal from its subtree: depth, blocked subgoals, open knowledge
gaps, accumulated failures, open contradictions, and how long the goal has stalled.
Above a threshold, the organization engine *proposes* a team — an intention that
competes like any other. Reorganizing is never free and never automatic.

Which roles are proposed depends on which components of the pressure are elevated:
knowledge gaps suggest investigation, failures and contradictions suggest
validation, blockage and stalling suggest analysis, and a team of two or more gets
a synthesis unit.

## What units actually do

They propose. An `InvestigationAgent` proposes exploration weighted toward its
goal's subtree; a `ValidationAgent` plans its goal at a permissive confidence
threshold and proposes confirming the weakest assumption the plan depends on; an
`AnalysisAgent` searches far deeper than the goal engine affords itself and leaves
plan hints on the blackboard; a `SynthesisAgent` writes what the team achieved
into semantic memory.

None of them can execute anything. A team changes behaviour only by changing the
pressure landscape — which means an unhelpful team is outcompeted rather than
obeyed.

## Dissolution

A team dissolves when its purpose goal closes, when no unit has contributed within
the idle limit, or at maximum lifetime. Dissolution writes a team outcome to
semantic memory: roles, lifetime, contributions, reason. Over a long run this
accumulates into evidence about which organizational shapes were worth forming —
which is the question the whole mechanism exists to ask.

## Honest status

`no_organization` returns 18.4 against the full architecture's 44.9 across eight
seeds. Under our earlier drive-modulated configuration the same comparison showed
no difference at all, which is a caution about reading either number too hard at
n=8. Teams demonstrably form, contribute and dissolve for legible reasons; that
they help is now suggested rather than shown.

The sharpest caveat comes from an unrelated ablation: `no_curiosity` produces the
highest topology churn of any architecture (146.6) and returns 1.0. Teams forming
is not the same as organization working.
