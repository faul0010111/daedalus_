from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...agents.lifecycle import AgentLifecycle
    from ...cognition.planning.planner import Planner
    from ...core.events import EventBus
    from ...core.runtime.config import DaedalusConfig
    from ...core.state import Clock
    from ...experiments.simulations.base import Environment
    from ...goals import GoalEmergence, GoalGraph
    from ...intentions import IntentionPool
    from ...memory import MemorySystem
    from ...meta.performance import PerformanceMonitor
    from ...meta.strategy_evolution import StrategyRegistry
    from ...observability.metrics import AutonomyMetrics
    from ...observability.traces import Tracer
    from ...tools import ToolRegistry
    from ...world import WorldModel


@dataclass
class CognitiveContext:
    """Shared state visible to all cognitive processes (a blackboard, not a controller)."""

    config: "DaedalusConfig"
    clock: "Clock"
    bus: "EventBus"
    rng: random.Random
    env: "Environment"
    world: "WorldModel"
    goals: "GoalGraph"
    emergence: "GoalEmergence"
    pool: "IntentionPool"
    memory: "MemorySystem"
    tools: "ToolRegistry"
    planner: "Planner"
    strategies: "StrategyRegistry"
    metrics: "AutonomyMetrics"
    monitor: "PerformanceMonitor"
    tracer: "Tracer"
    agents: "AgentLifecycle"
    drives: dict[str, float] = field(default_factory=dict)
    blackboard: dict[str, Any] = field(default_factory=dict)
    distances: dict[str, int] = field(default_factory=dict)
