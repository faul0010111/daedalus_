# The intention economy

The core claim: if several cognitive processes can propose actions, and exactly
one proposal can be acted on per tick, then the scoring function *is* the
architecture — and it should be swappable, contextual and learnable rather than
hard-coded.

## Anatomy of an intention

```python
Intention(
    key="explore:r3_2",              # identity — proposals merge on this
    kind=IntentionKind.EXPLORE,
    target={"type": "explore", "entity": "r3_2"},
    features=IntentionFeatures(
        goal_alignment=..., expected_value=..., urgency=...,
        uncertainty_reduction=..., novelty=..., confidence=...,
        resource_cost=..., expected_information_gain=..., risk=...,
        historical_success_rate=...),
)
```

`key` matters: when the curiosity engine and an investigation unit independently
propose exploring the same place, they do not create two intentions — they create
one with `support == 2`, which earns a small bonus. Agreement between independent
processes is evidence.

## Scoring

The conceptual formula from the brief is the `linear` strategy, and — after
measurement — the default:

```
priority = Σ wᵢ · featureᵢ
```

The `contextual` strategy keeps that form but modulates the weights by the agent's
**drives** — internal pressures derived from state, not from goals:

| drive | derived from | effect on weights |
|---|---|---|
| `scarcity` | energy against its floor | `resource_cost` ×(1+2d), `urgency` ×(1+0.5d) |
| `fragility` | structural integrity | `risk` ×(1+1.5d) |
| `uncertainty` | critical uncertain beliefs, total entropy | information features ×(1+d) |
| `stagnation` | no progress over the window | `novelty` ×(1+2d) |
| `failure` | recent action failure rate | `confidence` ×(1+d) |

So the same intention, unchanged, wins when the agent is healthy and loses when it
is starving. Nothing in the code says "when energy is low, rest" — the ranking just
moves. `test_drives_reweigh_the_same_features` pins this behaviour.

It is also, on this testbed, worse than not doing it: `with_drives` returns 24.1
against 44.9 for fixed weights. It buys consistency (the lowest variance of any
competent architecture) and pays for it with the entire upper half of the
distribution. Hence `with_drives` is a preset rather than the default.

On top of the base score:

- **learned bias** per intention kind, updated from outcomes with a moving
  baseline: `bias ← bias + lr · tanh(reward/step − baseline)` — measured *harmful*
  (see `no_attention_learning` in the results), kept because a ratchet this legible
  is worth being able to reproduce;
- **support** bonus, logarithmic in the number of independent proposers;
- **habituation** penalty for recent failures on this exact intention and for
  intentions that have run long without finishing;
- **commitment** bonus for the incumbent focus, which is itself an adaptable
  decision point (`fickle` / `steady` / `stubborn`).

## Preemption

A challenger replaces the incumbent only if it beats it by more than
`preempt_margin`. Without this the agent thrashes between near-equals and finishes
nothing; with too much of it the agent ignores emergencies. It is a parameter of
the economy, not a rule about which kinds may interrupt which.

## Baselines

Two strategies exist to be beaten:

- `fixed_pipeline` — strict precedence by kind (risk → contradiction → goal →
  opportunity → explore → …), the architecture this project argues against.
  Measured result: it locks onto contradiction-resolution and never reaches a
  goal. Attention entropy exactly 0.
- `random` — uniform choice among the same intentions, isolating how much of the
  performance comes from *which* intentions exist versus *which one is chosen*.

## What attention does not do

It does not decide how to achieve anything. The winner is handed to deliberation,
which plans over beliefs and returns a single next step. If that step is
impossible, the intention fails, which is itself pressure — failure feeds
habituation, the failure memory, and the reflection engine's backlog.
