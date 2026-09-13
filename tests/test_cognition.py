"""Tests for the cognitive core.

These assert architectural properties — evidence accumulation, goal emergence,
attention competition, adaptation, determinism — not incidental behaviour.
"""
from __future__ import annotations

import asyncio

import pytest

from daedalus.cognition.planning import Target
from daedalus.cognition.reasoning import knowledge_gaps
from daedalus.core.runtime import Daedalus, DaedalusConfig
from daedalus.core.state import SQLiteStateStore
from daedalus.experiments.simulations.labyrinth import Labyrinth, LabyrinthConfig, door_id
from daedalus.goals import GoalKind, GoalStatus
from daedalus.intentions import IntentionFeatures, IntentionKind
from daedalus.intentions.model import Intention
from daedalus.world import EpistemicStatus, WorldModel, WorldSchema
from daedalus.world.beliefs import update


def make_agent(seed: int = 3, preset: str = "full", size: int = 5, **kwargs) -> Daedalus:
    env = Labyrinth(LabyrinthConfig(seed=seed, width=size, height=size))
    return Daedalus(env, DaedalusConfig.preset(preset, seed), **kwargs)


# =============================================================== world model
class TestWorldModel:
    def test_evidence_accumulates_and_opposing_evidence_lowers_confidence(self) -> None:
        world = WorldModel(WorldSchema(priors={"contains": 0.25}))
        first = world.observe("r1", "contains", "key", True, 0.9).belief.confidence
        second = world.observe("r1", "contains", "key", True, 0.9).belief.confidence
        assert second > first > 0.25
        after = world.observe("r1", "contains", "key", False, 0.99).belief.confidence
        assert after < second

    def test_reliability_governs_how_much_a_claim_moves_a_belief(self) -> None:
        assert update(0.5, True, 0.99) > update(0.5, True, 0.6) > 0.5

    def test_functional_predicate_excludes_alternatives(self) -> None:
        world = WorldModel(WorldSchema(functional={"at"}, priors={"at": 0.3}))
        world.observe("agent", "at", "r1", True, 0.99)
        world.observe("agent", "at", "r2", True, 0.99)
        assert world.confidence("agent", "at", "r1") < 0.3
        assert world.holds("agent", "at", "r2")

    def test_credible_counter_evidence_opens_a_contradiction(self) -> None:
        world = WorldModel(WorldSchema())
        for _ in range(4):
            world.observe("r1", "contains", "relic", True, 0.95)
        result = world.observe("r1", "contains", "relic", False, 0.99)
        assert result.contradiction is not None
        assert result.belief.status is EpistemicStatus.CONTRADICTED
        assert world.open_contradictions()

    def test_routine_sensor_noise_does_not_manufacture_contradictions(self) -> None:
        world = WorldModel(WorldSchema())
        for _ in range(4):
            world.observe("r1", "contains", "relic", True, 0.95)
        assert world.observe("r1", "contains", "relic", False, 0.7).contradiction is None

    def test_verification_grades_earlier_noisy_claims(self) -> None:
        world = WorldModel(WorldSchema())
        world.register_source("scan", 0.88)
        world.observe("r1", "contains", "relic", True, 0.88, "scan")
        world.observe("r1", "contains", "relic", False, 0.99, "probe")
        ledger = list(world.verification_ledger)
        assert ledger and ledger[0]["source"] == "scan" and ledger[0]["claimed"] is True
        assert ledger[0]["truth"] is False

    def test_volatile_beliefs_drift_back_toward_their_prior(self) -> None:
        now = {"t": 100}
        world = WorldModel(WorldSchema(volatile={"contains": 0.5}, priors={"contains": 0.25}),
                           tick_provider=lambda: now["t"])
        world.observe("r1", "contains", "relic", True, 0.95)
        high = world.confidence("r1", "contains", "relic")
        for _ in range(5):
            now["t"] += 4
            world.decay()
        assert world.confidence("r1", "contains", "relic") < high

    def test_queries_are_ordered_so_cognition_is_reproducible(self) -> None:
        world = WorldModel(WorldSchema())
        for name in ("zeta", "alpha", "mu"):
            world.observe("r1", "contains", name, True, 0.9)
        assert world.objects("r1", "contains") == sorted(world.objects("r1", "contains"))


# ================================================================== planning
class TestPlanning:
    def test_plan_is_found_for_a_reachable_target(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(6))
        here = agent.env.agent_room
        neighbour = sorted(agent.env.adjacency[here])[0]
        plan = agent.ctx.planner.plan(agent.ctx, Target.fact(("agent", "at", neighbour)))
        assert plan.executable and plan.steps[0][0] == "move"

    def test_relaxation_reports_a_blocker_rather_than_failing_silently(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        asyncio.run(agent.run(3))
        here = agent.env.agent_room
        beyond = "vaultroom"
        ctx.world.observe(here, "connected", beyond, True, 0.99)
        ctx.world.observe(beyond, "is_a", "location", True, 0.99)
        ctx.world.observe(door_id(here, beyond), "locked", "gold", True, 0.99)
        plan = ctx.planner.plan(ctx, Target.fact(("agent", "at", beyond)))
        assert plan.found and not plan.executable
        assert (("agent", "holding", "key:gold"), True) in plan.violations

    def test_weakest_assumption_sets_plan_confidence(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(8))
        ctx = agent.ctx
        here = agent.env.agent_room
        target = sorted(agent.env.adjacency[here])[0]
        plan = ctx.planner.plan(ctx, Target.fact(("agent", "at", target)))
        if plan.support:
            assert plan.success <= min(ctx.world.confidence(*f) for f in plan.support) + 1e-9

    def test_knowledge_gap_is_found_by_regression_over_capabilities(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(4))
        gaps = knowledge_gaps(agent.ctx, ("thread", "deposited", "yes"))
        assert ("?room", "contains", "thread") in gaps


# ============================================================ goal emergence
class TestGoalEmergence:
    def test_unknown_dependency_becomes_an_emergent_know_goal(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(40))
        emergent = [g for g in agent.ctx.goals.goals.values() if g.emergent]
        assert emergent, "no goal emerged from the knowledge gap"
        assert any(g.kind is GoalKind.KNOW for g in emergent)
        child = emergent[0]
        assert agent.ctx.goals.parents(child.id), "emergent goal is not attached to its parent"

    def test_emergent_goals_are_deduplicated_not_duplicated(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(120))
        signatures = [g.signature for g in agent.ctx.goals.goals.values() if g.status.open]
        assert len(signatures) == len(set(signatures))

    def test_subgoal_inherits_importance_from_what_it_serves(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(40))
        for goal in agent.ctx.goals.goals.values():
            for parent in agent.ctx.goals.parents(goal.id):
                if parent.status.open:
                    assert agent.ctx.goals.value(goal.id) <= agent.ctx.goals.value(parent.id) + 1e-9

    def test_goal_closes_when_the_world_model_says_it_holds(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        goal = ctx.goals.add("test", GoalKind.ACHIEVE, pattern=("x", "is_a", "y"), importance=0.5)
        for _ in range(4):
            ctx.world.observe("x", "is_a", "y", True, 0.99)
        asyncio.run(agent.run(1))
        assert ctx.goals.goals[goal.id].status is GoalStatus.ACHIEVED

    def test_persistent_goal_reopens_when_its_condition_is_lost(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        goal = ctx.goals.add("persist", GoalKind.ACHIEVE, pattern=("x", "is_a", "y"), persistent=True)
        for _ in range(4):
            ctx.world.observe("x", "is_a", "y", True, 0.99)
        asyncio.run(agent.run(1))
        assert ctx.goals.goals[goal.id].status is GoalStatus.ACHIEVED
        for _ in range(6):
            ctx.world.observe("x", "is_a", "y", False, 0.99)
        asyncio.run(agent.run(1))
        assert ctx.goals.goals[goal.id].status is GoalStatus.ACTIVE

    def test_goal_graph_refuses_cycles(self) -> None:
        agent = make_agent()
        graph = agent.ctx.goals
        a = graph.add("a", GoalKind.ACHIEVE, pattern=("a", "p", "o"))
        b = graph.add("b", GoalKind.ACHIEVE, pattern=("b", "p", "o"), parent=a.id)
        from daedalus.goals.graph import EdgeKind
        graph.link(a.id, b.id, EdgeKind.SUBGOAL)
        assert graph.depth(b.id) == 1


# ========================================================= attention economy
def _intention(key: str, kind: IntentionKind, **features) -> Intention:
    return Intention(key=key, kind=kind, description=key, target={"type": "cognitive", "op": "reflect"},
                     features=IntentionFeatures(**features).clamp())


class TestAttentionEconomy:
    def test_higher_value_intention_wins_attention(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        ctx.pool.propose(ctx, _intention("weak", IntentionKind.EXPLORE, expected_value=0.1), "t")
        ctx.pool.propose(ctx, _intention("strong", IntentionKind.EXPLORE, expected_value=0.9,
                                         goal_alignment=0.9), "t")
        assert agent.attention.allocate(ctx).focal.key == "strong"

    def test_drives_reweigh_the_same_features(self) -> None:
        agent = make_agent(preset="with_drives")
        ctx = agent.ctx
        cheap = ctx.pool.propose(ctx, _intention("cheap", IntentionKind.EXPLORE, expected_value=0.5,
                                                 resource_cost=0.1), "t")
        pricey = ctx.pool.propose(ctx, _intention("pricey", IntentionKind.EXPLORE, expected_value=1.0,
                                                  resource_cost=0.6), "t")
        ctx.drives = {"scarcity": 0.0}
        assert agent.attention.allocate(ctx).focal.key == "pricey"
        agent.attention.focal_key = None
        ctx.drives = {"scarcity": 1.0}
        assert agent.attention.allocate(ctx).focal.key == "cheap"
        assert cheap.last_score > pricey.last_score

    def test_fixed_weights_ignore_drives(self) -> None:
        """The default architecture scores the same whatever the agent's state."""
        agent = make_agent()
        ctx = agent.ctx
        ctx.pool.propose(ctx, _intention("pricey", IntentionKind.EXPLORE, expected_value=1.0,
                                         resource_cost=0.6), "t")
        ctx.drives = {"scarcity": 0.0}
        calm = agent.attention.allocate(ctx).ranking[0].final
        agent.attention.focal_key = None  # otherwise the commitment bonus confounds the comparison
        ctx.drives = {"scarcity": 1.0}
        assert agent.attention.allocate(ctx).ranking[0].final == pytest.approx(calm)

    def test_intentions_expire_when_nothing_keeps_proposing_them(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        ctx.pool.propose(ctx, _intention("transient", IntentionKind.EXPLORE, expected_value=0.4), "t")
        for _ in range(ctx.config.limits.intention_ttl + 2):
            ctx.clock.advance()
        ctx.pool.expire_stale(ctx, protected=set())
        assert "transient" not in ctx.pool.live

    def test_multiple_proposers_of_one_intention_add_support(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        ctx.pool.propose(ctx, _intention("shared", IntentionKind.VALIDATE, expected_value=0.4), "a")
        shared = ctx.pool.propose(ctx, _intention("shared", IntentionKind.VALIDATE, expected_value=0.4), "b")
        assert shared.support == 2 and shared.sources == {"a", "b"}

    def test_commitment_prevents_thrashing_between_near_equals(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        agent.attention.focal_key = "incumbent"
        inc = ctx.pool.propose(ctx, _intention("incumbent", IntentionKind.EXPLORE, expected_value=0.5), "t")
        inc.status = inc.status.ACTIVE
        ctx.pool.propose(ctx, _intention("challenger", IntentionKind.EXPLORE, expected_value=0.52), "t")
        assert agent.attention.allocate(ctx).focal.key == "incumbent"

    def test_repeated_failure_habituates_attention_away(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        target = _intention("sticky", IntentionKind.EXPLORE, expected_value=0.6)
        ctx.pool.propose(ctx, target, "t")
        before = agent.attention.allocate(ctx).ranking[0].final
        for _ in range(3):
            agent.attention.record_outcome(ctx.clock.tick, "sticky", False)
        assert agent.attention.allocate(ctx).ranking[0].final < before


# ================================================= reflection and adaptation
class TestReflectionAndAdaptation:
    def test_reflection_learns_that_a_noisy_source_is_less_reliable(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        ctx.world.register_source("scan", 0.88)
        for i in range(8):
            room = f"room{i}"
            ctx.world.observe(room, "contains", "ghost", True, 0.88, "scan")
            ctx.world.observe(room, "contains", "ghost", False, 0.99, "probe")
        before = ctx.world.sources["scan"].estimate
        agent.reflection.execute(ctx, None)
        assert ctx.world.sources["scan"].estimate < before
        assert ctx.memory.semantic.get("source:scan") is not None

    def test_repeated_failures_are_diagnosed_and_recorded_as_a_lesson(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        for _ in range(4):
            ctx.memory.failure.record(ctx.clock.tick, "take", {"item": "relic:1"}, "not_present",
                                      "exploit_opportunity", belief_source="scan")
        insights = agent.reflection.execute(ctx, None)
        assert any(i["type"] == "failure_pattern" and i["cause"] == "scan" for i in insights)
        assert ctx.memory.semantic.get("failure:take:not_present") is not None

    def test_a_trial_is_adopted_when_the_system_improves_beyond_the_noise(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        point = "exploration.frontier_policy"
        for tick in range(10):
            ctx.strategies.system_history.append((tick, 0.0))
        ctx.clock.tick = 20
        trial = ctx.strategies.start_trial(ctx, point, "unit test")
        assert trial is not None and trial.baseline_samples
        for tick in range(21, 41):
            ctx.strategies.system_history.append((tick, 1.0))
        ctx.clock.tick = 41
        for _ in range(ctx.strategies.trial_length):
            ctx.strategies.record(ctx, point, trial.candidate, 0.0)
        assert point not in ctx.strategies.trials
        assert ctx.strategies.points[point].incumbent == trial.candidate
        audit = ctx.memory.strategic.audit[-1]
        assert audit.decision == "adopted"
        assert audit.evidence["measure"].startswith("system")

    def test_a_trial_is_rejected_when_the_system_does_not_improve(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        point = "planning.support_threshold"
        incumbent = ctx.strategies.points[point].incumbent
        for tick in range(10):
            ctx.strategies.system_history.append((tick, 1.0))
        ctx.clock.tick = 20
        trial = ctx.strategies.start_trial(ctx, point, "unit test")
        for tick in range(21, 41):
            ctx.strategies.system_history.append((tick, 0.2))
        ctx.clock.tick = 41
        for _ in range(ctx.strategies.trial_length):
            ctx.strategies.record(ctx, point, trial.candidate, 5.0)  # looks great locally
        assert ctx.strategies.points[point].incumbent == incumbent
        assert ctx.memory.strategic.audit[-1].decision == "rejected"

    def test_a_locally_rewarding_strategy_cannot_buy_adoption(self) -> None:
        """Per-intention reward must not override a flat system-level result."""
        agent = make_agent()
        ctx = agent.ctx
        point = "opportunity.min_confidence"
        for tick in range(12):
            ctx.strategies.system_history.append((tick, 0.5))
        ctx.clock.tick = 20
        trial = ctx.strategies.start_trial(ctx, point, "unit test")
        for tick in range(21, 41):
            ctx.strategies.system_history.append((tick, 0.5))
        ctx.clock.tick = 41
        for _ in range(ctx.strategies.trial_length):
            ctx.strategies.record(ctx, point, trial.candidate, 10.0)
        assert ctx.memory.strategic.audit[-1].decision == "rejected"

    def test_attention_policy_learns_from_outcomes(self) -> None:
        agent = make_agent()
        assert agent.policy is not None
        agent.policy.update(IntentionKind.EXPLORE, 2.0, 1, 10)
        assert agent.policy.bias["explore"] > 0
        agent.policy.update(IntentionKind.VALIDATE, -2.0, 1, 11)
        assert agent.policy.bias["validate"] < 0

    def test_consolidation_turns_episodes_into_reusable_statistics(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(80))
        ctx = agent.ctx
        assert agent.consolidation is not None
        result = agent.consolidation.execute(ctx, None)
        assert result["signatures"] > 0
        assert not ctx.memory.episodic.unconsolidated()
        assert any(k.kind == "statistic" for k in ctx.memory.semantic.items.values())


# ============================================================ self-organization
class TestOrganization:
    def test_complexity_pressure_rises_with_blocked_subgoals(self) -> None:
        from daedalus.agents.topology import complexity_pressure
        agent = make_agent()
        ctx = agent.ctx
        root = ctx.goals.roots()[0]
        base, _ = complexity_pressure(ctx, root.id)
        child = ctx.goals.add("blocked child", GoalKind.KNOW, pattern=("?a", "contains", "x"),
                              parent=root.id, origin="emergent:test")
        ctx.goals.transition(child.id, GoalStatus.BLOCKED, "test")
        after, _ = complexity_pressure(ctx, root.id)
        assert after > base

    def test_units_are_spawned_and_dissolved_when_their_purpose_closes(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        root = ctx.goals.roots()[0]
        units = ctx.agents.spawn_team(ctx, root.id, ["investigation", "analysis"], "test")
        assert len(units) == 2 and len(ctx.agents.processes()) == 2
        ctx.goals.transition(root.id, GoalStatus.ACHIEVED, "test")
        ctx.agents.upkeep(ctx)
        assert not ctx.agents.units
        assert any(k.kind == "team_outcome" for k in ctx.memory.semantic.items.values())

    def test_idle_units_are_dissolved(self) -> None:
        agent = make_agent()
        ctx = agent.ctx
        root = ctx.goals.roots()[0]
        ctx.agents.spawn_team(ctx, root.id, ["investigation"], "test")
        ctx.clock.tick += ctx.agents.idle_limit + 1
        ctx.agents.upkeep(ctx)
        assert not ctx.agents.units


# ================================================================== runtime
class TestRuntime:
    def test_a_tick_produces_a_traceable_decision(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(12))
        trace = agent.ctx.tracer.latest()
        assert trace and trace["ranking"]
        assert "contributions" in trace["ranking"][0]["base"]

    def test_runs_are_reproducible_for_a_fixed_seed(self) -> None:
        def fingerprint() -> tuple:
            agent = make_agent(seed=11)
            asyncio.run(agent.run(150))
            return (agent.env.task_metrics(), len(agent.ctx.world.beliefs),
                    sorted(g.signature for g in agent.ctx.goals.goals.values()),
                    agent.ctx.metrics.counters.get("actions"))
        assert fingerprint() == fingerprint()

    def test_different_architectures_behave_differently(self) -> None:
        results = {}
        for preset in ("full", "fixed_pipeline"):
            agent = make_agent(seed=4, preset=preset)
            asyncio.run(agent.run(200))
            results[preset] = agent.ctx.monitor.summary()["kind_share"]
        assert results["full"] != results["fixed_pipeline"]
        assert len(results["fixed_pipeline"]) <= len(results["full"])

    def test_every_preset_runs_without_error(self) -> None:
        for preset in DaedalusConfig.PRESETS:
            agent = make_agent(seed=2, preset=preset)
            asyncio.run(agent.run(60))
            assert agent.clock.tick == 60

    def test_events_carry_the_whole_cognitive_cycle(self) -> None:
        agent = make_agent()
        asyncio.run(agent.run(60))
        categories = {e.category for e in agent.bus.history}
        assert {"perception", "world", "intention", "attention", "action", "evaluation"} <= categories

    def test_state_snapshot_round_trips(self, tmp_path) -> None:
        store = SQLiteStateStore(tmp_path / "t.db")
        agent = make_agent(store=store)
        asyncio.run(agent.run(60))
        agent.save()
        snapshot = store.load_snapshot(agent.config.run_id)
        restored = make_agent(store=store)
        restored.load(snapshot)
        assert restored.clock.tick == agent.clock.tick
        assert len(restored.ctx.world.beliefs) == len(agent.ctx.world.beliefs)
        assert restored.env.agent_room == agent.env.agent_room
        asyncio.run(restored.run(5))

    def test_console_state_is_serializable(self) -> None:
        import json
        agent = make_agent()
        asyncio.run(agent.run(50))
        payload = json.dumps(agent.state(), default=str)
        assert len(payload) > 2000

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_agent_makes_progress_on_the_task(self, seed: int) -> None:
        agent = make_agent(seed=seed, size=4)
        asyncio.run(agent.run(600))
        metrics = agent.env.task_metrics()
        banked = metrics["relic_value_banked"] + metrics["threads_recovered"]
        assert banked > 0 or agent.ctx.metrics.counters.get("emergent_goals", 0) > 0
        assert agent.ctx.world.cumulative_uncertainty_reduction > 1.0
