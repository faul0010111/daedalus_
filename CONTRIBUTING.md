# Contributing to DAEDALUS

DAEDALUS is a research architecture, so contributions are judged less by whether
they make the agent score higher and more by whether they make a claim testable.

## Ground rules

1. **Never report a number you did not measure.** Every figure in `docs/` comes
   from `results/report.json`, produced by `python -m daedalus.cli experiment`.
   If you change behaviour, re-run the ablations and update both.
2. **Capabilities are engineered; behaviour is emergent.** A pull request that
   hard-codes "if the key is missing, go find the key" will be declined. Add the
   *capability* (a tool, a predicate, a generator, a decision point) and let the
   attention economy decide when it matters.
3. **No cognitive process may call another.** Processes read shared state and
   propose intentions. If you find yourself wanting `planner.call(critic)`, what
   you want is an intention the critic can win.
4. **Determinism is load-bearing.** Never iterate a `set` where the order can
   affect behaviour — sort it. `test_runs_are_reproducible_for_a_fixed_seed`
   guards this, but it only catches what it covers.

## Development

```bash
pip install -e ".[dev]"
pytest                              # cognitive core
node tests/console_render.js        # console, against a captured API state
python -m daedalus.cli run --ticks 800
```

## Adding a new environment

Implement `daedalus.experiments.simulations.base.Environment`: declare a
`WorldSchema`, the tools that exist, the sources that can be observed and their
claimed reliability, and the initial goals. Nothing in `core/`, `intentions/`,
`goals/` or `cognition/` should need to change — if it does, that is a bug in
the separation, and worth an issue on its own.

## Adding an architecture preset

Presets live in `DaedalusConfig.preset()` and must be listed in `PRESETS`. Two
places also need to agree: the console's dropdown in `frontend/index.html`, and
`docs/experiments/results.md`, which must never describe a preset the code no
longer produces. A change to a *default* is a change to what `full` means, and
therefore invalidates every published figure until the ablations are re-run.

## Adding a strategy variant

Register it in `STRATEGY_POINTS` (`core/runtime/engine.py`) and make the
intentions that depend on it record the active variant in `intention.strategies`.
The adaptation loop will trial it on its own; do not wire in when it should be used.

## Proposing an experiment

Open an issue with the hypothesis, the preset or ablation that tests it, and the
metric that would falsify it. Results that contradict the README are the most
valuable kind of contribution here.
