"""The DAEDALUS runtime.

The substrate does four things per tick: let due processes run, let attention
allocate, let the focal intention take one step, and let evaluation feed back.
It never decides *what* to think about — that is the whole point.
"""
from __future__ import annotations

import random
from typing import Any

from ...agents.lifecycle import AgentLifecycle
from ...agents.topology import OrganizationEngine
from ...cognition.adaptation import AdaptationEngine
from ...cognition.perception import PerceptionLoop, ingest
from ...cognition.planning import Planner
from ...cognition.planning.deliberation import Deliberator, StepDecision
from ...cognition.reasoning import distances_from, position
from ...cognition.reflection import ReflectionEngine
from ...experiments.simulations.base import Environment
from ...goals import GoalEmergence, GoalGraph, GoalKind, GoalStatus
from ...intentions import Intention, IntentionKind, IntentionPool, IntentionStatus
from ...intentions.attention import AttentionEconomy
from ...intentions.generators.contradiction import ContradictionEngine
from ...intentions.generators.curiosity import CuriosityEngine
from ...intentions.generators.goal_engine import GoalEngine
from ...intentions.generators.opportunity import OpportunityEngine
from ...intentions.generators.risk import RiskEngine
from ...memory import MemorySystem
from ...memory.consolidation import MemoryConsolidationLoop
from ...meta.performance import PerformanceMonitor, TickRecord
from ...meta.self_evaluation import MetaCognitiveLayer
from ...meta.strategy_evolution import StrategyRegistry
from ...observability.metrics import AutonomyMetrics
from ...observability.traces import Tracer
from ...tools import ToolRegistry
from ...tools.evaluation import OutcomeEvaluator
from ...tools.execution import ToolExecutor
from ...world import WorldModel
from ..cognition.context import CognitiveContext
from ..events import EventBus, EventType
from ..state import Clock, SQLiteStateStore
from .config import DaedalusConfig

GENERATORS = {
    "goal": GoalEngine,
    "curiosity": CuriosityEngine,
    "contradiction": ContradictionEngine,
    "opportunity": OpportunityEngine,
    "risk": RiskEngine,
    "reflection": ReflectionEngine,
}

STRATEGY_POINTS = [
    ("exploration.frontier_policy", "How the next place to explore is chosen.",
     {"nearest": "nearest", "max_gain": "max_gain", "gain_per_cost": "gain_per_cost"}, "gain_per_cost"),
    ("planning.support_threshold", "Minimum belief confidence a plan may rely on.",
     {"cautious": 0.7, "balanced": 0.55, "bold": 0.4}, "balanced"),
    ("opportunity.min_confidence", "Minimum confidence before chasing a sighted opportunity.",
     {"trusting": 0.45, "guarded": 0.65, "strict": 0.85}, "guarded"),
    ("risk.energy_reserve", "Projected energy margin below which mitigation becomes urgent.",
     {"cautious": 40.0, "balanced": 25.0, "daring": 15.0}, "balanced"),
    ("attention.temperature", "Softmax temperature over intention scores (0 = strict argmax).",
     {"deterministic": 0.0, "warm": 0.12, "hot": 0.3}, "deterministic"),
    ("attention.commitment", "Bonus that keeps attention on the current focus.",
     {"fickle": 0.0, "steady": 0.18, "stubborn": 0.45}, "steady"),
]


class Daedalus:
    def __init__(self, env: Environment, config: DaedalusConfig | None = None,
                 store: SQLiteStateStore | None = None) -> None:
        self.config = config or DaedalusConfig()
        self.env = env
        self.store = store
        self.clock = Clock()
        self.bus = EventBus(lambda: self.clock.tick)
        self.rng = random.Random(self.config.seed)

        world = WorldModel(env.schema, self.bus, lambda: self.clock.tick)
        for name, reliability in env.sources().items():
            world.register_source(name, reliability)
        tools = ToolRegistry()
        for spec in env.capabilities():
            tools.register(spec)

        strategies = StrategyRegistry()
        for name, description, variants, incumbent in STRATEGY_POINTS:
            strategies.define(name, description, variants, incumbent, adaptable=self.config.adaptation)
        strategies.enabled = self.config.adaptation

        goals = GoalGraph(self.bus, lambda: self.clock.tick)
        self.ctx = CognitiveContext(
            config=self.config, clock=self.clock, bus=self.bus, rng=self.rng, env=env, world=world,
            goals=goals,
            emergence=GoalEmergence(self.config.limits.max_goal_depth, self.config.limits.max_open_goals),
            pool=IntentionPool(self.config.limits.intention_ttl, self.config.limits.intention_capacity),
            memory=MemorySystem(self.config.limits.working_memory, self.config.limits.episodic_capacity),
            tools=tools, planner=Planner(), strategies=strategies, metrics=AutonomyMetrics(),
            monitor=PerformanceMonitor(), tracer=Tracer(), agents=AgentLifecycle(self.config.limits.max_agents),
        )
        self.ctx.blackboard.update({"unreflected": [], "adapt_requests": {}, "plan_hints": {}, "trail": [],
                                    "maintenance_candidates": {}, "maintenance_baseline": {}})

        self.perception = PerceptionLoop()
        self.generators = [GENERATORS[name]() for name in self.config.generators]
        self.reflection: ReflectionEngine = next(
            (g for g in self.generators if isinstance(g, ReflectionEngine)), ReflectionEngine())
        self.adaptation = AdaptationEngine() if self.config.adaptation else None
        self.metacognition = MetaCognitiveLayer() if self.config.metacognition else None
        self.organization = OrganizationEngine() if self.config.organization else None
        self.consolidation = MemoryConsolidationLoop() if self.config.consolidation else None
        self.deliberator = Deliberator()
        self.executor = ToolExecutor()
        self.evaluator = OutcomeEvaluator()

        from ...intentions.prioritization import (DEFAULT_WEIGHTS, ContextualPriority, FixedPipelinePolicy,
                                                  LearnedAttentionPolicy, LinearPriority, RandomPolicy)
        strategy = {"contextual": ContextualPriority, "linear": LinearPriority,
                    "fixed_pipeline": FixedPipelinePolicy, "random": RandomPolicy}[self.config.attention.policy]
        weights = dict(self.config.attention.weights or DEFAULT_WEIGHTS)
        if not self.config.attention.memory_feedback:
            # scoped ablation: memory still records, consolidates and diagnoses —
            # it just no longer reaches the score through past success rates
            weights["historical_success_rate"] = 0.0
        strategy_instance = strategy(weights) if strategy in (ContextualPriority, LinearPriority) \
            else strategy()
        self.policy = LearnedAttentionPolicy() if self.config.attention.learning else None
        self.attention = AttentionEconomy(strategy_instance, self.policy,
                                          self.config.attention.background_slots,
                                          self.config.attention.background_threshold,
                                          self.config.attention.preempt_margin,
                                          self.config.attention.starvation_bonus)
        self.history: list[dict[str, Any]] = []
        self.started = False
        self._seed_goals()

    # ---------------------------------------------------------------- bootstrap
    def _seed_goals(self) -> None:
        for spec in self.env.initial_goals():
            self.ctx.goals.add(spec["description"], GoalKind(spec["kind"]), pattern=spec.get("pattern"),
                               quantity=spec.get("quantity"), threshold=spec.get("threshold", 0.0),
                               comfort=spec.get("comfort"),
                               importance=spec.get("importance", 0.5), persistent=spec.get("persistent", False),
                               origin="developer", reason="initial goal")

    @property
    def processes(self) -> list[Any]:
        procs: list[Any] = [self.perception, *self.generators]
        for extra in (self.adaptation, self.metacognition, self.organization, self.consolidation):
            if extra is not None:
                procs.append(extra)
        procs.extend(self.ctx.agents.processes())
        return procs

    # --------------------------------------------------------------------- tick
    async def tick(self) -> dict[str, Any]:
        ctx = self.ctx
        tick = self.clock.advance()
        self.started = True

        for change in self.env.advance(tick):
            self.bus.publish(EventType.ENV_DYNAMICS, "environment", change)

        # --- perception: the world writes into the world model
        await self.perception.run(ctx)
        ctx.world.decay()
        self._refresh_context()

        # --- pressure: every due process proposes, none of them decides
        for process in self.processes:
            if process is self.perception or not process.due(tick):
                continue
            await process.run(ctx)

        focal_before = self.attention.focal_key
        ctx.pool.expire_stale(ctx, protected={focal_before} if focal_before else set())

        # baseline-only escape hatch: scheduled reflection for the fixed pipeline
        if self.config.fixed_reflection_period and tick % self.config.fixed_reflection_period == 0:
            self.reflection.execute(ctx, None)

        # --- attention: intentions compete
        decision = self.attention.allocate(ctx)
        focal = decision.focal
        record = {"tick": tick, "focal": focal.key if focal else None,
                  "kind": focal.kind.value if focal else None, "tool": None, "success": None,
                  "reward": 0.0, "candidates": len(decision.ranking)}

        # --- background slot: a low-cost internal op runs alongside the focus
        internal_ops = 0
        for background in decision.background:
            self._run_internal(background, ctx)
            internal_ops += 1

        info_gain = 0.0
        energy_before = ctx.world.quantities.get("energy", 0.0)
        if focal is not None:
            outcome = await self._advance(focal, ctx)
            record.update(outcome)
            info_gain = outcome.get("info_gain", 0.0)
            internal_ops += outcome.get("internal", 0)

        progress = ctx.goals.achieved_value() - self._achieved_before if hasattr(self, "_achieved_before") else 0.0
        self._achieved_before = ctx.goals.achieved_value()
        ctx.monitor.record_tick(TickRecord(
            tick, record["kind"], record["tool"], record["success"], record["reward"], info_gain,
            max(0.0, energy_before - ctx.world.quantities.get("energy", 0.0)), max(0.0, progress), internal_ops))
        ctx.metrics.inc("internal_operations", internal_ops)
        self._update_drives()
        if tick % 5 == 0:
            ctx.strategies.observe_system(ctx)
            ctx.world.sample_evolution()
            ctx.metrics.sample(tick, {"uncertainty": round(ctx.world.total_uncertainty(), 3),
                                      "beliefs": len(ctx.world.beliefs),
                                      "open_goals": len(ctx.goals.open_goals()),
                                      "live_intentions": len(ctx.pool.live),
                                      **{k: round(v, 3) for k, v in ctx.drives.items()}})
        if self.organization is not None:
            ctx.agents.upkeep(ctx)
        self.history.append(record)
        del self.history[:-1000]
        return record

    async def run(self, ticks: int) -> list[dict[str, Any]]:
        return [await self.tick() for _ in range(ticks)]

    # ------------------------------------------------------------------ context
    def _refresh_context(self) -> None:
        ctx = self.ctx
        here = position(ctx)
        ctx.distances = distances_from(ctx, here)
        ctx.blackboard["_explore_value"] = {}
        if here:
            trail = ctx.blackboard.setdefault("trail", [])
            if not trail or trail[-1] != here:
                trail.append(here)
                del trail[:-200]
        from ...intentions.generators.curiosity import rank_frontier
        ctx.blackboard["frontier_size"] = len(rank_frontier(ctx, "gain_per_cost", min_value=0.25))
        # places the agent could walk to but has never actually examined
        ctx.blackboard["virgin_frontier"] = [
            place for place in ctx.world.entities_of_type(ctx.world.schema.explorable_type)
            if place in ctx.distances
            and any((place, p) not in ctx.world.coverage for p in ctx.world.schema.epistemic)]
        ctx.memory.working.push(ctx.clock.tick, "position", place=here,
                                energy=ctx.world.quantities.get("energy"),
                                integrity=ctx.world.quantities.get("integrity"))

    def _update_drives(self) -> None:
        ctx = self.ctx
        q = ctx.world.quantities
        critical = ctx.world.critical_uncertain(0.3, 0.8)
        ctx.drives = {
            "scarcity": max(0.0, min(1.0, 1 - q.get("energy", 100) / 60)),
            "fragility": max(0.0, min(1.0, 1 - q.get("integrity", 100) / 70)),
            "uncertainty": min(1.0, len(critical) / 4 + min(ctx.world.total_uncertainty() / 60, 0.5)),
            "stagnation": ctx.monitor.stagnation(),
            "failure": ctx.monitor.failure_pressure(),
        }

    # ---------------------------------------------------------------- execution
    def _run_internal(self, intention: Intention, ctx: CognitiveContext) -> None:
        op = intention.target.get("op")
        done = True
        if op == "reflect":
            insights = self.reflection.execute(ctx, intention)
            intention.reward += 0.05 * len(insights)
        elif op == "consolidate" and self.consolidation is not None:
            result = self.consolidation.execute(ctx, intention)
            intention.reward += 0.02 * result["signatures"]
        elif op == "adapt" and self.adaptation is not None:
            done = self.adaptation.execute(ctx, intention)
            intention.reward += 0.1 if done else -0.05
        elif op == "spawn_team" and self.organization is not None:
            done = self.organization.execute(ctx, intention)
            intention.reward += 0.1 if done else -0.05
        intention.target["done"] = True
        intention.steps += 1
        ctx.memory.record_outcome(intention.kind.value, done)
        self._finish(intention, ctx, IntentionStatus.COMPLETED if done else IntentionStatus.FAILED,
                     f"internal:{op}")

    async def _advance(self, intention: Intention, ctx: CognitiveContext) -> dict[str, Any]:
        out: dict[str, Any] = {"tool": None, "success": None, "reward": 0.0, "info_gain": 0.0, "internal": 0}
        decision: StepDecision = self.deliberator.next_step(ctx, intention)
        if decision.kind == "internal":
            self._run_internal(intention, ctx)
            out["internal"] = 1
            out["reward"] = intention.reward
            return out
        if decision.kind == "complete":
            self._finish(intention, ctx, IntentionStatus.COMPLETED, decision.reason)
            return out
        if decision.kind == "fail":
            if intention.goal_id and intention.goal_id in ctx.goals.goals:
                goal = ctx.goals.goals[intention.goal_id]
                goal.failures += 1
                if decision.reason in ("blocked", "no_plan"):
                    ctx.goals.transition(goal.id, GoalStatus.BLOCKED, f"deliberation: {decision.reason}")
            self._finish(intention, ctx, IntentionStatus.FAILED, decision.reason)
            return out

        tool, args = decision.tool, decision.args
        before = {"achieved_value": ctx.goals.achieved_value(),
                  "banked_value": ctx.world.quantities.get("banked_value", 0.0)}
        result = await self.executor.execute(ctx, tool, args, intention.id)
        report = ingest(ctx, result.percept)
        if intention.target["type"] == "verify":
            intention.target["verified"] = True
        if intention.target["type"] == "tool":
            intention.target["done"] = True
        episode = self.evaluator.evaluate(ctx, intention, tool, args, result, report, before)

        intention.steps += 1
        intention.reward += episode.reward
        if intention.goal_id and intention.goal_id in ctx.goals.goals:
            ctx.goals.goals[intention.goal_id].attempts += 1
        if result.success:
            intention.consecutive_failures = 0
        else:
            intention.step_failures += 1
            intention.consecutive_failures += 1
            intention.plan = []
            intention.plan_revision = -1
        ctx.metrics.inc("actions")
        if intention.origin not in ("goal_engine",) or (intention.goal_id and
                                                        ctx.goals.goals[intention.goal_id].emergent):
            ctx.metrics.inc("self_initiated_actions")
        ctx.metrics.inc("uncertainty_reduction", report.entropy_reduction)
        ctx.agents.credit(intention.origin, ctx.clock.tick)
        ctx.memory.working.push(ctx.clock.tick, "action", tool=tool, args=args, success=result.success,
                                reward=round(episode.reward, 3))
        if ctx.tools.get(tool).maintains:
            ctx.blackboard.setdefault("maintenance_last_used", {})[tool] = ctx.clock.tick
            ctx.blackboard.get("maintenance_candidates", {}).pop(tool, None)
        out.update({"tool": tool, "success": result.success, "reward": episode.reward,
                    "info_gain": report.entropy_reduction})
        if self.deliberator.is_complete(ctx, intention):
            self._finish(intention, ctx, IntentionStatus.COMPLETED, "target satisfied")
        return out

    def _finish(self, intention: Intention, ctx: CognitiveContext, status: IntentionStatus, outcome: str) -> None:
        success = status is IntentionStatus.COMPLETED
        if success and not intention.kind.internal:
            intention.reward += 0.25 * intention.features.expected_value
        ctx.pool.finish(ctx, intention, status, outcome)
        self.attention.release(intention.key)
        self.attention.record_outcome(ctx.clock.tick, intention.key, success)
        ctx.monitor.record_intention(ctx.clock.tick, intention.kind.value, success)
        ctx.memory.record_outcome(intention.kind.value, success)
        signature = f"{intention.kind.value}:{intention.target.get('type')}"
        ctx.memory.record_outcome(signature, success)
        if self.policy is not None:
            self.policy.update(intention.kind, intention.reward, max(1, intention.steps), ctx.clock.tick)
        for point, variant in intention.strategies.items():
            ctx.strategies.record(ctx, point, variant, intention.reward / max(1, intention.steps))
        ctx.metrics.inc("preemptions", 0)
        if intention.goal_id and intention.goal_id in ctx.goals.goals and not success:
            ctx.goals.goals[intention.goal_id].failures += 1

    # ------------------------------------------------------------- persistence
    def snapshot(self) -> dict[str, Any]:
        ctx = self.ctx
        return {
            "tick": self.clock.tick, "config": self.config.model_dump(), "rng": self.rng.getstate(),
            "world": ctx.world.to_dict(), "env": self.env.to_dict(),
            "goals": {"goals": [g.to_dict() for g in ctx.goals.goals.values()],
                      "edges": [[c, p, k.value, t] for c, p, k, t in ctx.goals.edges],
                      "seq": ctx.goals._seq},
            "metrics": dict(ctx.metrics.counters),
            "semantic": [k.to_dict() for k in ctx.memory.semantic.items.values()],
            "strategies": {name: p.incumbent for name, p in ctx.strategies.points.items()},
            "policy": self.policy.bias if self.policy else None,
            "task": self.env.task_metrics(),
        }

    def save(self) -> None:
        if self.store:
            self.store.save_snapshot(self.config.run_id, self.clock.tick, self.snapshot())
            self.store.append_events(self.config.run_id, [e.to_dict() for e in self.bus.recent(400)])

    def load(self, snapshot: dict[str, Any]) -> None:
        from ...goals.graph import EdgeKind, Goal, GoalStatus as GS
        ctx = self.ctx
        self.clock.tick = snapshot["tick"]
        state = snapshot["rng"]
        self.rng.setstate((state[0], tuple(state[1]), state[2]))
        ctx.world.load_dict(snapshot["world"])
        self.env.load_dict(snapshot["env"])
        ctx.goals.goals.clear()
        for g in snapshot["goals"]["goals"]:
            goal = Goal(g["id"], g["description"], GoalKind(g["kind"]),
                        tuple(g["pattern"]) if g["pattern"] else None, g["quantity"], g["threshold"],
                        g.get("comfort", 0.0),
                        g["importance"], g["origin"], g["persistent"], GS(g["status"]), g["created"],
                        g["updated"], g["achieved"], g["stalls"], g["attempts"], g["failures"],
                        g["block_reason"], [tuple(h) for h in g["history"]])
            ctx.goals.goals[goal.id] = goal
        for c, p, k, t in snapshot["goals"]["edges"]:
            ctx.goals.link(c, p, EdgeKind(k))
        ctx.goals._seq = snapshot["goals"]["seq"]
        ctx.metrics.counters.update(snapshot["metrics"])
        for name, incumbent in snapshot["strategies"].items():
            if name in ctx.strategies.points:
                ctx.strategies.points[name].incumbent = incumbent
        if self.policy and snapshot["policy"]:
            self.policy.bias.update(snapshot["policy"])

    # ------------------------------------------------------------ introspection
    def state(self) -> dict[str, Any]:
        from ...observability.graphs import agent_topology, intention_graph, memory_graph, world_view
        from ...observability.timelines import cognitive_timeline
        ctx = self.ctx
        focal = self.attention.focal_key
        return {
            "tick": self.clock.tick, "run_id": self.config.run_id, "config": self.config.model_dump(),
            "world": world_view(ctx),
            "goals": ctx.goals.to_dict(),
            "intentions": {"live": [i.to_dict() for i in sorted(ctx.pool.live.values(),
                                                                key=lambda i: i.last_score, reverse=True)],
                           "archive": [i.to_dict() for i in list(ctx.pool.archive)[-30:]],
                           "graph": intention_graph(ctx, focal), "focal": focal,
                           "decision": ctx.tracer.latest(), "traces": list(ctx.tracer.decisions)[-40:]},
            "agents": agent_topology(ctx, self.processes) | ctx.agents.to_dict(),
            "memory": ctx.memory.summary() | {
                "graph": memory_graph(ctx),
                "semantic": [k.to_dict() for k in sorted(ctx.memory.semantic.items.values(),
                                                         key=lambda k: k.updated_tick, reverse=True)[:40]],
                "working": ctx.memory.working.to_list(),
                "episodes": [e.to_dict() for e in ctx.memory.episodic.recent(25)],
                "failures": [f.to_dict() for f in ctx.memory.failure.records[-15:]],
                "insights": self.reflection.insights[-25:]},
            "meta": {"performance": ctx.monitor.summary(), "drives": {k: round(v, 3) for k, v in ctx.drives.items()},
                     "diagnoses": ctx.blackboard.get("diagnoses", []),
                     "diagnosis_history": self.metacognition.history[-40:] if self.metacognition else [],
                     "strategies": ctx.strategies.to_dict(ctx),
                     "policy": {"bias": self.policy.bias, "updates": self.policy.updates,
                                "history": self.policy.history[-120:]} if self.policy else None,
                     "processes": [p.describe() for p in self.processes],
                     "planner": {"calls": ctx.planner.calls, "expansions": ctx.planner.total_expansions,
                                 "failures": ctx.planner.failures, "replans": self.deliberator.replans}},
            "metrics": ctx.metrics.autonomy(self.clock.tick, ctx.world.cumulative_uncertainty_reduction) |
                       {"series": list(ctx.metrics.series)[-240:]},
            "events": cognitive_timeline(self.bus, 160),
            "task": self.env.task_metrics(),
            "ground_truth": self.env.ground_truth(),
            "history": self.history[-160:],
        }
