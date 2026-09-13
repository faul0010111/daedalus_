# DAEDALUS

**A self-directed architecture for persistent agentic intelligence.**

> *Engineer the capabilities. Let intelligence organize the behavior.*

DAEDALUS is an experimental architecture for agents whose behaviour is not a
workflow. The developer declares what the agent *can* do — tools, observable
environments, memory stores, resource limits, initial goals — and declines to
say what it *should* do next. Behaviour emerges from several cognitive processes
competing, continuously, for a single scarce resource: attention.

There is no `if failure: run_critic()` anywhere in this repository. There is a
market for intentions, and reflection is something that has to win.

---

## The hypothesis

> Can behaviour emerge from the continuous interaction of goals, uncertainty,
> curiosity, contradiction, opportunity, memory, reflection and the capacity to act?

Partly — and the interesting part is *which* parts, including the components of
our own design that the measurements do not support. See
[docs/experiments/results.md](docs/experiments/results.md) for what the ablations
actually show, including the components that turned out not to earn their place.

---

## Quick start

```bash
pip install -e ".[dev]"

python -m daedalus.cli run --ticks 1500        # headless, prints emergent goals
python -m daedalus.cli serve                   # research console at http://127.0.0.1:8000
python -m daedalus.cli experiment --ticks 2500 # ablations across seeds → results/
pytest                                         # 43 tests over the cognitive core
```

The console needs no build step: FastAPI serves `frontend/` directly.

---

## How it works

```
                        ┌──────────────────────┐
                        │      ENVIRONMENT     │
                        └──────────┬───────────┘
                                   ▼
                             PERCEPTION ──────────────► WORLD MODEL
                                                    (beliefs, confidence,
                                                     contradictions, hypotheses)
                                                            │
       ┌──────────┬────────────┬───────────┬────────────┬───┴──────┐
       ▼          ▼            ▼           ▼            ▼          ▼
     goals    curiosity   contradiction  opportunity   risk    reflection
       └──────────┴────────────┴───────────┴────────────┴──────────┘
                                   ▼
                          INTENTION ECONOMY          ◄── drives modulate weights
                                   ▼                     (scarcity, fragility,
                          ATTENTION ALLOCATION            uncertainty, stagnation,
                                   ▼                      failure)
                        DELIBERATION → ACTION
                                   ▼
                    OBSERVATION → EVALUATION → MEMORY
                                   ▼
                     REFLECTION → ADAPTATION → (back into the economy)
```

Every tick: perception writes into the world model; every *due* process proposes
intentions; the economy scores them; one wins; the winner takes exactly one step.
No process calls another. The runtime never decides what to think about — that is
the entire point, and `core/runtime/engine.py` is deliberately short.

### The intention economy

Six generators propose intentions carrying the ten attributes from the brief
(`goal_alignment`, `expected_value`, `urgency`, `uncertainty_reduction`,
`novelty`, `confidence`, `resource_cost`, `expected_information_gain`, `risk`,
`historical_success_rate`). The priority function is **not fixed**: four
strategies ship (`linear`, `contextual`, `fixed_pipeline`, `random`). The
`contextual` one modulates its weights by the agent's internal drives — low energy
makes cost heavier, stagnation makes novelty attractive, recent failure makes
confidence matter more — and a learned policy can add a per-kind bias from
outcomes. Both are implemented, instrumented, and measured *worse* than plain fixed
weights on this testbed, so the default is linear and they are opt-in presets. The
architecture is the competition; the scoring sophistication was a hypothesis, and
it lost.

Intentions persist only while something keeps proposing them. Nothing is
scheduled; pressure has to be sustained.

### Goal emergence

Goals form a **dynamic graph**, not a task list: they emerge, split, merge,
suspend, get abandoned and reactivate. Two mechanisms create them, both by
reasoning over declared capabilities rather than by hand-written rules:

- **Knowledge gaps** — regression over tool preconditions: *to deposit the thread
  I must hold it; to hold it I must know where it is; I don't.* → a `KNOW` goal.
- **Relaxed planning** — the planner may violate *relaxable* preconditions at a
  penalty. The cheapest violating plan names the blocker. → an `ACHIEVE` goal.

Run the agent and watch this chain assemble itself with nothing scripted:

```
g1 blocked   Return the Thread of Ariadne to the Atrium   knowledge gap: ?room contains thread
g4 blocked   Discover ?room such that ?room contains thread   frontier exhausted; r5_1 is behind a barrier
g8 achieved  Make true: agent at r5_1
g9 achieved  Make true: agent holding key:gold
g7 achieved  Discover ?room such that ?room contains key:silver
```

### The world model

Beliefs accumulate evidence in log-odds space, weighted by a *learned* estimate
of each source's reliability — the environment's sensor claims 92% accuracy, and
the agent finds out for itself whether that is true. Every belief carries an
epistemic status (`observed_fact`, `inferred_belief`, `hypothesis`, `uncertain`,
`contradicted`) and a confidence. Functional predicates propagate exclusivity as
a probability constraint. Coverage turns silence into evidence of absence: *I
examined this room and did not see the relic.*

When credible evidence opposes a confident belief, a **contradiction** opens —
and generates pressure, not an interrupt.

### Self-organization

When complexity pressure on a goal rises — depth, blocked subgoals, knowledge
gaps, failures, stalling — the organization engine *proposes* a temporary team
(investigation / analysis / validation / synthesis). It competes for attention
like anything else. Units add focused proposals to the same economy; they command
nothing. When their purpose closes or they stop contributing, they dissolve and
their outcome is written to semantic memory.

### Meta-cognition

A monitor watches success rate, efficiency, tool usage, attention entropy,
stagnation and planning depth, and emits diagnoses in the language of the brief —
*Current strategy causing stagnation*, *Excessive tool usage detected*,
*Repeated failure pattern identified*. Diagnoses generate intentions. Adaptation
trials an alternative at a decision point and adopts it only if the *system's*
reward-plus-information per tick improves by more than the noise it sits in.
Every decision lands in an auditable record.

---

## The testbed

`Labyrinth` is a partially observable, non-stationary grid built to exercise each
pressure separately: unknown map (curiosity), locked passages (dependency
emergence), a noisy scanner that drifts with use and can be recalibrated
(contradiction, source learning, hypothesis formation), moving hazards (risk),
respawning relics and oil (opportunity, resource maintenance), and a thread that
slips back into the maze whenever it is returned — so the task never ends and
memory has to pay for itself.

The environment knows nothing about cognition. It declares tools and emits
percepts. Any environment implementing the same port works without touching a
line of `core/`, `intentions/`, `goals/` or `cognition/`.

---

## What the experiments show

Eight seeds, 2500 ticks each. `value` is what reached the atrium, in the
environment's own units (a thread is worth 10); `±` is the standard deviation
across seeds.

| architecture | mean | median | ± | emergent goals | gaps resolved |
|---|---|---|---|---|---|
| **no attention learning** | **54.6** | **59.5** | 36.6 | 9.6 | 5.4 |
| full | 44.9 | 17.5 | 47.1 | 6.4 | 3.6 |
| no metacognition | 39.1 | 21.5 | 47.9 | 5.5 | 2.9 |
| static weights | 33.5 | 25.0 | 33.8 | 6.6 | 3.0 |
| with drives | 24.1 | 22.5 | 16.2 | 4.0 | 1.5 |
| no memory feedback | 24.1 | 20.0 | 16.5 | 3.4 | 0.8 |
| starvation bonus | 22.9 | 20.5 | 14.9 | 3.5 | 1.0 |
| no organization | 18.4 | 19.0 | 12.4 | 2.8 | 0.6 |
| no reflection | 17.1 | 12.0 | 21.7 | 3.9 | 1.5 |
| random attention | 4.4 | 4.0 | 2.9 | 3.2 | 0.6 |
| no curiosity | 1.0 | 0.0 | 2.8 | 1.1 | 0.1 |
| **fixed pipeline** | **0.0** | 0.0 | 0.0 | 1.4 | 0.4 |

Read honestly:

- **Rigid workflows fail completely.** The fixed pipeline — strict precedence by
  intention kind, the architecture a sensible engineer would write — returns 0.0 on
  every seed. Attention entropy 0.00, epistemic tool share 1.00: every action it
  takes is a probe. Contradictions outrank goals in its precedence, a noisy sensor
  generates them faster than probing clears them, and it never reaches the third
  rule in its own list. Not a bug — obedience, forever.
- **Curiosity is load-bearing.** Remove it and the agent returns 1.0, while
  producing the *highest* team churn of any architecture: stalled goals keep
  forming and dissolving units. Paralysis that reads as adaptability.
- **Attention allocation carries most of the value.** Identical intentions, chosen
  at random: 4.4 against 44.9.
- **Our own learning mechanism hurts.** `no_attention_learning` is the best
  architecture measured — median 59.5 against the full system's 17.5 — and it
  produces *more* emergent goals and resolves *more* knowledge gaps. The learned
  per-kind bias is a ratchet: kinds that paid off win more, alternatives stop
  generating outcomes to learn from, and four of eight seeds never recover a thread
  at all.
- **Drive modulation does not pay for itself**, which is why fixed linear weights
  are the default here and `with_drives` is an opt-in preset. It is the most
  consistent competent architecture and gives up the entire upper half of the
  distribution to get there.
- **Our fix for attention lock-in failed, instructively.** An optimism bonus toward
  neglected intention kinds flattened the distribution instead of lifting the floor:
  it stopped the agent committing to the thread loop, which is where nearly all the
  value is. Specialization was producing the results, not the pathology we took it
  for.

Full analysis, per-seed distributions and limitations:
[docs/experiments/results.md](docs/experiments/results.md).

## Documentation

- [Architecture](docs/architecture/overview.md) — the substrate, and why it is thin
- [Intention economy](docs/architecture/intention-economy.md) — scoring, drives, preemption
- [World model](docs/architecture/world-model.md) — evidence, contradiction, source learning
- [Goal emergence](docs/architecture/goals.md) — the dynamic goal graph
- [Memory](docs/architecture/memory.md) — five stores and consolidation
- [Self-organization](docs/architecture/agents.md) — temporary cognitive units
- [Research questions](docs/research/questions.md) — the seven questions, and where each stands
- [Autonomy metrics](docs/autonomy/metrics.md) — what they measure and how each can be gamed
- [Experiments](docs/experiments/results.md) — full results, method, limitations

---

## Stack

Python 3.11+, FastAPI, Pydantic, asyncio. The agent runtime is written here
rather than delegated to an agent framework — a framework that supplies the loop
would be supplying the answer to the research question. Persistence is a port:
SQLite ships as the reference adapter, PostgreSQL / vector / graph stores
implement the same protocol. The console is dependency-free vanilla JS and SVG.

## Status

Experimental, and honest about it. The architecture is complete and instrumented;
the agent's competence on its testbed is modest and high-variance. Both facts are
measured, reproducible with a fixed seed, and reported above.

Apache 2.0. Contributions that falsify something here are especially welcome —
see [CONTRIBUTING.md](CONTRIBUTING.md).
