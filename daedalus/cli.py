"""DAEDALUS command line: run, serve, experiment, replay."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .core.runtime import Daedalus, DaedalusConfig
from .core.state import SQLiteStateStore
from .experiments.benchmarks import main_sync, summarize
from .experiments.simulations.labyrinth import Labyrinth, LabyrinthConfig


def build_agent(args) -> Daedalus:
    env = Labyrinth(LabyrinthConfig(seed=args.seed, width=args.size, height=args.size))
    config = DaedalusConfig.preset(args.preset, args.seed)
    store = SQLiteStateStore(args.db) if getattr(args, "db", None) else None
    return Daedalus(env, config, store)


def cmd_run(args) -> None:
    agent = build_agent(args)

    async def go() -> None:
        every = max(1, args.ticks // 10)
        for start in range(0, args.ticks, every):
            await agent.run(min(every, args.ticks - start))
            task = agent.env.task_metrics()
            print(f"t{agent.clock.tick:<6} threads={task['threads_recovered']:.0f} "
                  f"banked={task['relic_value_banked']:.0f} goals={len(agent.ctx.goals.goals)} "
                  f"emergent={agent.ctx.metrics.counters.get('emergent_goals', 0)} "
                  f"beliefs={len(agent.ctx.world.beliefs)} energy={task['energy']:.0f}")
    asyncio.run(go())
    agent.save()
    state = agent.state()
    print("\nautonomy metrics")
    for key, value in state["metrics"].items():
        if key != "series":
            print(f"  {key:<28} {value}")
    print("\nemergent goals")
    for goal in state["goals"]["goals"]:
        if goal["origin"].startswith("emergent"):
            print(f"  {goal['id']:<5} {goal['status']:<10} {goal['description'][:64]}")
    if args.json:
        Path(args.json).write_text(json.dumps(state, indent=1, default=str))
        print(f"\nfull state written to {args.json}")


def cmd_serve(args) -> None:
    import uvicorn

    from .api.server import create_app
    uvicorn.run(create_app(build_agent(args)), host=args.host, port=args.port, log_level="warning")


def cmd_experiment(args) -> None:
    presets = args.presets or list(DaedalusConfig.PRESETS)
    report = main_sync(presets, args.seeds, args.ticks, Path(args.out), args.checkpoints)
    print("\n" + summarize(report))
    print(f"\nwritten to {args.out}/report.json and {args.out}/runs.json")


def main() -> None:
    parser = argparse.ArgumentParser(prog="daedalus", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, default=7)
    common.add_argument("--size", type=int, default=6, help="labyrinth grid size")
    common.add_argument("--preset", default="full", choices=list(DaedalusConfig.PRESETS))

    run = sub.add_parser("run", parents=[common], help="run the agent headless")
    run.add_argument("--ticks", type=int, default=1500)
    run.add_argument("--db", default=None, help="sqlite file for snapshots")
    run.add_argument("--json", default=None, help="write the full final state to this path")
    run.set_defaults(func=cmd_run)

    serve = sub.add_parser("serve", parents=[common], help="serve the research console API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", default=None)
    serve.set_defaults(func=cmd_serve)

    exp = sub.add_parser("experiment", help="run ablations across seeds")
    exp.add_argument("--presets", nargs="*", choices=list(DaedalusConfig.PRESETS))
    exp.add_argument("--seeds", nargs="*", type=int, default=[1, 2, 3, 4, 5])
    exp.add_argument("--ticks", type=int, default=2000)
    exp.add_argument("--out", default="results")
    exp.add_argument("--checkpoints", type=int, default=0, help="record a checkpoint every N ticks")
    exp.set_defaults(func=cmd_experiment)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
