# The world model

A persistent, probabilistic model of the environment in which every element
carries a confidence and an epistemic status, and in which the *reliability of
each source is itself learned*.

## Evidence

Beliefs are triples with a confidence updated in log-odds space:

```
logit(c') = logit(c) ± logit(reliability)
```

Reliability is the weight of a claim, so a 0.99 source moves a belief much
further than a 0.7 source, and repeated weak evidence converges slowly rather
than not at all. Confidence is clamped away from 0 and 1 so no belief becomes
unrevisable.

## Epistemic status

| status | meaning |
|---|---|
| `observed_fact` | strong direct evidence, confidence at an extreme |
| `inferred_belief` | derived or accumulated, confident but not directly witnessed |
| `hypothesis` | asserted by the agent to be tested, not observed |
| `uncertain` | confidence in the middle band where action is a gamble |
| `contradicted` | credible evidence stands against a confident belief |

## Exclusivity as a constraint

For a functional predicate (`agent at ?`), believing `at r2` with confidence *c*
implies `at r1` is no more likely than *1 − c*. This is applied as a **cap**, not
as another piece of evidence — probability, not persuasion. `contains` is
inverse-functional: one object sits in one place.

## Coverage: silence as evidence

A percept reports not only what was seen but what was *examined*:
`(room, "contains", reliability, source)`. Anything believed to be in that room
and not reported is observed to be absent, at the source's reliability. Without
this an agent can only ever gain beliefs, never retire them.

## Contradiction

A contradiction opens when credible direct evidence (effective reliability ≥ 0.85)
opposes a confident belief (≥ 0.85 or ≤ 0.15). The threshold matters: too low and
ordinary sensor noise manufactures contradictions faster than they can be cleared —
which is precisely the failure mode the `fixed_pipeline` baseline exhibits, and
which `test_routine_sensor_noise_does_not_manufacture_contradictions` guards
against here.

A contradiction does not interrupt anything. It generates pressure through the
contradiction engine, weighted by whether the fact is relevant to an open goal or
marked critical by a current plan.

## Learning what a source is worth

Each source has a Beta posterior over "claims that survive verification", with
exponential forgetting so the estimate tracks drift instead of averaging it away.
When strong evidence (≥ 0.95) settles a fact, earlier weak claims about that fact
are graded in a verification ledger. The reflection engine consumes the ledger and
updates the posteriors.

The effective reliability used for updates is the *minimum* of the claimed and the
learned value: a source may not talk its way up, only down.

This is where one of the more satisfying behaviours comes from. The Labyrinth's
scanner degrades with use and can be recalibrated. The agent is never told this.
It observes its scanner's accuracy falling, notices a tool declaring
`maintains="scan"`, forms the hypothesis *"scan degrades with use; calibrate may
restore it"*, and — if the resulting intention wins attention — tests it by
comparing accuracy before and after.

## Quantities and criticality

Continuous resources (energy, integrity) are tracked separately from beliefs, with
history, because they are observed exactly rather than inferred. Facts that a
current plan depends on are marked *critical* for a short window, which is what
makes the risk engine propose validating them specifically — the agent checks
what it is about to rely on, not whatever happens to be uncertain.
