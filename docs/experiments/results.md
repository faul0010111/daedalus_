# Experiments

Everything here comes from `results/report.json` and `results/runs.json`, produced by:

```bash
python -m daedalus.cli experiment --seeds 1 2 3 4 5 6 7 8 --ticks 2500 --checkpoints 500
```

Runs are deterministic for a fixed seed, so every figure below is reproducible.

## Method

Eight labyrinth layouts (seeds 1–8), 2500 ticks each, twelve architectures. The
seed controls the environment *and* the agent's RNG, so every architecture faces
exactly the same eight worlds.

**Outcome measure.** `value_returned` — what reached the atrium, in the
environment's own units. A returned thread is worth 10 (the environment's own
figure); relics are worth 1–5. It is the only measure that combines the persistent
goal and the opportunistic one without our picking a weighting after the fact.

**Baseline.** `full` is linear weights, learned attention bias on, adaptation,
metacognition and organization on, all six generators. Each ablation changes one
thing:

| preset | what changes |
|---|---|
| `fixed_pipeline` | economy replaced by strict precedence by intention kind; reflection every 20 ticks |
| `random_attention` | uniform choice among the same intentions |
| `with_drives` | the same weights, modulated by internal drives |
| `no_attention_learning` | no learned per-kind bias (adaptation still on) |
| `static_weights` | no learned bias *and* no strategy adaptation |
| `no_memory_feedback` | consolidated success rates no longer reach the score |
| `starvation_bonus` | optimism toward intention kinds attention has stopped choosing |
| `no_curiosity` / `no_reflection` / `no_metacognition` / `no_organization` | that subsystem disabled |

## Results

| architecture | mean | median | stdev | per-seed values (sorted) |
|---|---|---|---|---|
| **no attention learning** | **54.6** | **59.5** | 36.6 | 7 11 32 37 82 86 91 91 |
| full | 44.9 | 17.5 | 47.1 | 3 8 12 14 21 85 98 118 |
| no metacognition | 39.1 | 21.5 | 47.9 | 3 5 8 18 25 28 91 135 |
| static weights | 33.5 | 25.0 | 33.8 | 0 5 8 23 27 37 75 93 |
| with drives | 24.1 | 22.5 | 16.2 | 7 9 13 22 23 25 39 55 |
| no memory feedback | 24.1 | 20.0 | 16.5 | 4 6 16 17 23 37 43 47 |
| starvation bonus | 22.9 | 20.5 | 14.9 | 5 13 14 19 22 25 31 54 |
| no organization | 18.4 | 19.0 | 12.4 | 0 5 13 18 20 22 34 35 |
| no reflection | 17.1 | 12.0 | 21.7 | 3 5 10 12 12 12 13 70 |
| random attention | 4.4 | 4.0 | 2.9 | 0 2 3 4 4 6 7 9 |
| no curiosity | 1.0 | 0.0 | 2.8 | 0 0 0 0 0 0 0 8 |
| fixed pipeline | 0.0 | 0.0 | 0.0 | 0 0 0 0 0 0 0 0 |

Supporting diagnostics (means):

| architecture | attention entropy | epistemic share | emergent goals | gaps resolved | reflections |
|---|---|---|---|---|---|
| no attention learning | 1.18 | 0.20 | 9.6 | 5.4 | 45.8 |
| full | 1.37 | 0.13 | 6.4 | 3.6 | 47.8 |
| random attention | 1.61 | 0.15 | 3.2 | 0.6 | 349.6 |
| no curiosity | 0.20 | 0.05 | 1.1 | 0.1 | 4.4 |
| fixed pipeline | 0.00 | 1.00 | 1.4 | 0.4 | 798.2 |

## What this supports

**Rigid cognitive workflows fail completely — the strongest result here.**
`fixed_pipeline` returns exactly 0.0 on all eight seeds. Attention entropy 0.00,
epistemic tool share 1.00: every single action it takes is a probe. The mechanism
is worth stating precisely, because it is the failure the project predicts. Strict
precedence puts contradiction-resolution above goal pursuit; a scanner with 8–42%
noise generates contradictions faster than probing clears them; the agent never
reaches the third rule in its own precedence list. It is not stuck in a bug. It is
obeying its precedence, forever.

**Curiosity is load-bearing.** Without it the agent returns 1.0, and produces the
*highest* topology churn of any architecture (146.6 against 61.1) — goals stall
permanently, stalling raises complexity pressure, and teams form and dissolve in a
loop. Paralysis that reads as adaptability.

**Attention allocation carries most of the value.** The same intention set under
uniform random selection returns 4.4 against 44.9. The generators are identical in
both arms, so this isolates *selection* from *proposal*.

**Reflection and organization now look load-bearing too.** `no_reflection` 17.1 and
`no_organization` 18.4, against 44.9. Under our earlier drive-modulated
configuration these differences sat inside the noise; under fixed weights they are
large and consistent. Not conclusive at n=8, but no longer ambiguous in direction.

## What this refutes — including our own design

**The learned attention bias hurts.** `no_attention_learning` is the best
architecture measured: mean 54.6 against 44.9, and median **59.5 against 17.5**.
Its worst seed returns 7, while `full`'s worst three return 3, 8 and 12. It also
produces half again as many emergent goals (9.6 vs 6.4) and resolves 50% more
knowledge gaps. Turning off a learning mechanism made the agent more autonomous by
our own metrics.

The likely mechanism is a ratchet: the policy biases toward intention kinds that
paid off, the bias makes those kinds win more, and the alternatives stop generating
outcomes to learn from. The per-seed thread counts show its shape — `full`:
`0 0 0 11 8 0 0 8`, four seeds that never recover a thread at all, against
`no_attention_learning`: `2 8 0 3 0 7 8 8`.

**Drive modulation does not pay for itself.** `with_drives` returns 24.1/22.5
against 44.9/17.5. It is the most *consistent* competent architecture — the lowest
variance of any working arm — but it trades away the upper half of the
distribution. The default configuration in this repository is therefore plain
linear weights; drives are an implemented option the data currently argues against.

**Memory feedback into the score is not demonstrated to help.** Zeroing the
`historical_success_rate` feature gives 24.1/20.0: lower mean, marginally higher
median, much lower variance. This was the missing experiment named in an earlier
draft of the research questions, and the answer is a shrug — past success rates
shape the tail, not the typical run. The ablation is scoped: memory still records,
consolidates, diagnoses failures and drives adaptation; only the path into the
priority score is cut.

**Our fix for attention lock-in did not work.** `starvation_bonus` adds optimism
toward kinds attention has stopped choosing. It returns 22.9/20.5 against
44.9/17.5, and compressed the distribution — stdev 14.9 against 47.1 — by removing
the upper tail rather than lifting the floor. Its per-seed thread counts are
`0 0 0 0 0 0 0 5`: forcing attention to keep sampling every kind stopped the agent
from ever committing to the thread loop, which is where nearly all the value is.
Specialization was producing the results, not the pathology we took it for.

That correction matters, because an earlier version of this document blamed the
variance on the learned policy. The data says otherwise. With learning off the
variance stays high (stdev 36.6) and the whole distribution shifts *up*. High
variance is a property of the task — the thread loop is worth an order of magnitude
more than relics, and finding it depends partly on the layout — while the learned
bias is what depresses the median.

## The failure mode we can name

The weakest seeds fall into an energy-poverty trap: too low on energy to travel, so
the agent rests; resting produces no information; it never learns where the oil is;
it stays poor. The meta-cognitive layer *correctly* diagnoses `STAGNATION` and
`PLANNING_INEFFECTIVE` throughout — the self-model is accurate — but no available
strategy variant changes the outcome. We added `risk.energy_reserve` as a lever
specifically for this and it was not enough.

Accurate self-diagnosis without an effective remedy is, we suspect, a general shape
of failure for this kind of architecture, and worth naming.

## Limitations

- **Eight seeds is underpowered** for everything except the extremes
  (`fixed_pipeline`, `no_curiosity`, `random_attention`). We report standard
  deviations rather than significance tests because the latter would be theatre at
  n=8. The `no_attention_learning` result is the one we would most want replicated
  at n=40 before anyone builds on it.
- **Ablations are not independent.** `static_weights` removes both learning and
  adaptation; comparing it with `no_attention_learning` (33.5 vs 54.6) hints that
  adaptation helps once learning is off, but that is a two-factor inference from a
  one-factor design.
- **One environment.** Conclusions are about DAEDALUS-on-Labyrinth, which was built
  to exercise these pressures — a fair test of the mechanisms, a poor test of
  generality.
- **The outcome measure embeds a judgement.** Valuing a thread at 10 is the
  environment's own figure, but it still decides whether a thread-specialist beats a
  relic-specialist, and given the lock-in dynamics that choice moves the rankings.
- **No LLM in the loop.** Every process here is symbolic: cheap, deterministic and
  legible, and no evidence that the approach survives contact with a language-model
  reasoner.

## Reproducing and extending

```bash
python scripts/run_ablation.py no_attention_learning 1,2,3,4,5,6,7,8 2500 500
python -m daedalus.cli run --preset fixed_pipeline --ticks 1000 --json trace.json
python -m daedalus.cli serve --preset no_curiosity      # watch a failure mode live
```

The console's Strategy tab shows every trial and its evidence; the Metrics tab plots
uncertainty and autonomy over time. Watching `fixed_pipeline` for sixty seconds
explains its 0.0 better than this document does.
