#!/usr/bin/env python3
"""Run one preset's ablation and merge it into results/runs.json + report.json.

Split per preset so each invocation is short; the merged report is identical to
running them all at once.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daedalus.experiments.benchmarks import aggregate, run_once, summarize  # noqa: E402
from daedalus.experiments.benchmarks.harness import RunResult  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    preset = sys.argv[1]
    seeds = [int(s) for s in sys.argv[2].split(",")]
    ticks = int(sys.argv[3]) if len(sys.argv) > 3 else 2500
    checkpoints = int(sys.argv[4]) if len(sys.argv) > 4 else 500
    OUT.mkdir(exist_ok=True)

    results: list[RunResult] = []
    for seed in seeds:
        r = asyncio.run(run_once(preset, seed, ticks, checkpoints))
        results.append(r)
        print(f"{preset:<17} seed {seed}  value={r.task['value_returned']:.0f} "
              f"threads={r.task['threads_recovered']:.0f} "
              f"banked={r.task['relic_value_banked']:.0f} emergent={r.goals['emergent']} "
              f"gaps={r.autonomy['knowledge_gaps_resolved']} adapt={r.autonomy['strategy_adaptations']} "
              f"({r.seconds:.1f}s)", flush=True)

    runs_path, report_path = OUT / "runs.json", OUT / "report.json"
    runs = json.loads(runs_path.read_text()) if runs_path.exists() else []
    runs = [r for r in runs if not (r["preset"] == preset and r["ticks"] == ticks)]
    runs += [r.to_dict() for r in results]
    runs_path.write_text(json.dumps(runs, indent=1))

    report = json.loads(report_path.read_text()) if report_path.exists() else \
        {"ticks": ticks, "seeds": seeds, "presets": {}}
    report["ticks"] = ticks
    report["seeds"] = sorted(set(report.get("seeds", [])) | set(seeds))
    report["presets"][preset] = aggregate(results)
    report_path.write_text(json.dumps(report, indent=1))
    print("\n" + summarize(report))


if __name__ == "__main__":
    main()
