"""Experiment harness: run presets across seeds and report autonomy and task metrics.

Nothing here invents numbers. Every figure in docs/experiments comes from
`python -m daedalus.cli experiment`, which writes results/*.json.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...core.runtime import Daedalus, DaedalusConfig
from ..simulations.labyrinth import Labyrinth, LabyrinthConfig

TASK_KEYS = ("threads_recovered", "relic_value_banked", "collapses", "damage_taken", "exhausted_ticks",
             "first_thread_tick", "scans", "calibrations")
THREAD_VALUE = 10.0  # the thread's worth in the environment's own units
AUTONOMY_KEYS = ("self_initiated_ratio", "emergent_goals", "knowledge_gaps_resolved", "strategy_adaptations",
                 "agent_topology_changes", "reflection_events", "uncertainty_reduction", "goal_progress_rate",
                 "contradictions_resolved", "diagnoses")


@dataclass
class RunResult:
    preset: str
    seed: int
    ticks: int
    task: dict[str, float]
    autonomy: dict[str, Any]
    performance: dict[str, Any]
    goals: dict[str, int]
    strategies: dict[str, str]
    attention: dict[str, float]
    seconds: float
    checkpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"preset": self.preset, "seed": self.seed, "ticks": self.ticks, "task": self.task,
                "autonomy": self.autonomy, "performance": self.performance, "goals": self.goals,
                "strategies": self.strategies, "attention": self.attention,
                "seconds": round(self.seconds, 2), "checkpoints": self.checkpoints}


async def run_once(preset: str, seed: int, ticks: int, checkpoint_every: int = 0) -> RunResult:
    started = time.time()
    env = Labyrinth(LabyrinthConfig(seed=seed))
    agent = Daedalus(env, DaedalusConfig.preset(preset, seed))
    checkpoints: list[dict[str, Any]] = []
    remaining = ticks
    step = checkpoint_every or ticks
    while remaining > 0:
        await agent.run(min(step, remaining))
        remaining -= step
        if checkpoint_every:
            checkpoints.append({"tick": agent.clock.tick,
                                "threads": env.stats["threads_recovered"],
                                "banked": env.stats["relic_value_banked"],
                                "emergent_goals": agent.ctx.metrics.counters.get("emergent_goals", 0),
                                "uncertainty": round(agent.ctx.world.total_uncertainty(), 2)})
    ctx = agent.ctx
    goals = ctx.goals.goals.values()
    kinds = agent.ctx.monitor.summary()["kind_share"]
    return RunResult(
        preset=preset, seed=seed, ticks=ticks,
        task={k: env.task_metrics()[k] for k in TASK_KEYS} | {
            # one comparable figure: value returned to the atrium, in the environment's units
            "value_returned": env.stats["threads_recovered"] * THREAD_VALUE + env.stats["relic_value_banked"]},
        autonomy={k: ctx.metrics.autonomy(agent.clock.tick, ctx.world.cumulative_uncertainty_reduction)[k]
                  for k in AUTONOMY_KEYS},
        performance={k: agent.ctx.monitor.summary()[k] for k in
                     ("success_rate", "reward_per_tick", "info_gain_per_tick", "attention_entropy",
                      "epistemic_share")},
        goals={"total": len(goals), "achieved": sum(1 for g in goals if g.status.value == "achieved"),
               "emergent": sum(1 for g in goals if g.emergent),
               "abandoned": sum(1 for g in goals if g.status.value == "abandoned"),
               "blocked": sum(1 for g in goals if g.status.value == "blocked")},
        strategies={name: p.incumbent for name, p in ctx.strategies.points.items()},
        attention={k: round(v, 3) for k, v in kinds.items()},
        seconds=time.time() - started, checkpoints=checkpoints)


def aggregate(results: list[RunResult]) -> dict[str, Any]:
    def stat(values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        return {"mean": round(statistics.mean(values), 3),
                "median": round(statistics.median(values), 3),
                "stdev": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
                "min": round(min(values), 3), "max": round(max(values), 3)}

    out: dict[str, Any] = {"runs": len(results), "seeds": sorted(r.seed for r in results)}
    for group in ("task", "autonomy", "performance", "goals"):
        out[group] = {}
        keys = sorted({k for r in results for k in getattr(r, group)})
        for key in keys:
            values = [getattr(r, group)[key] for r in results
                      if isinstance(getattr(r, group).get(key), (int, float))]
            out[group][key] = stat(values)
    out["adopted_strategies"] = {}
    for name in results[0].strategies:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.strategies[name]] = counts.get(r.strategies[name], 0) + 1
        out["adopted_strategies"][name] = counts
    return out


async def experiment(presets: list[str], seeds: list[int], ticks: int, out_dir: Path,
                     checkpoint_every: int = 0, progress=print) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"ticks": ticks, "seeds": seeds, "presets": {}}
    runs: list[dict[str, Any]] = []
    for preset in presets:
        results = []
        for seed in seeds:
            result = await run_once(preset, seed, ticks, checkpoint_every)
            results.append(result)
            runs.append(result.to_dict())
            progress(f"  {preset:<16} seed {seed:<3} "
                     f"threads={result.task['threads_recovered']:.0f} "
                     f"banked={result.task['relic_value_banked']:.0f} "
                     f"emergent={result.goals['emergent']} "
                     f"({result.seconds:.1f}s)")
        report["presets"][preset] = aggregate(results)
    (out_dir / "runs.json").write_text(json.dumps(runs, indent=1))
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    return report


def summarize(report: dict[str, Any]) -> str:
    rows = [("preset", "value", "±", "threads", "banked", "emergent", "gaps", "adapt", "topology", "reflect")]
    for preset, agg in report["presets"].items():
        rows.append((
            preset,
            f"{agg['task']['value_returned']['mean']:.1f}",
            f"{agg['task']['value_returned']['stdev']:.1f}",
            f"{agg['task']['threads_recovered']['mean']:.1f}",
            f"{agg['task']['relic_value_banked']['mean']:.1f}",
            f"{agg['goals']['emergent']['mean']:.1f}",
            f"{agg['autonomy']['knowledge_gaps_resolved']['mean']:.1f}",
            f"{agg['autonomy']['strategy_adaptations']['mean']:.1f}",
            f"{agg['autonomy']['agent_topology_changes']['mean']:.1f}",
            f"{agg['autonomy']['reflection_events']['mean']:.1f}",
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(rows[0], widths)),
             "  ".join("-" * w for w in widths)]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows[1:]]
    return "\n".join(lines)


def main_sync(presets: list[str], seeds: list[int], ticks: int, out_dir: Path,
              checkpoint_every: int = 0) -> dict[str, Any]:
    return asyncio.run(experiment(presets, seeds, ticks, out_dir, checkpoint_every))
