from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field


class AttentionConfig(BaseModel):
    # Linear weights are the default because that is what the measurements support
    # (docs/experiments/results.md). Drive modulation is implemented and available as
    # the `with_drives` preset — it is an option the data currently argues against,
    # not the recommended baseline.
    policy: Literal["contextual", "linear", "fixed_pipeline", "random"] = "linear"
    learning: bool = True
    memory_feedback: bool = True   # let consolidated outcome statistics reach the score
    starvation_bonus: float = 0.0  # optimism toward intention kinds attention has abandoned
    background_slots: int = 1
    background_threshold: float = 0.55
    preempt_margin: float = 0.08
    weights: dict[str, float] | None = None


class LimitsConfig(BaseModel):
    max_open_goals: int = 24
    max_goal_depth: int = 4
    intention_ttl: int = 4
    intention_capacity: int = 80
    planner_expansions: int = 3000
    max_agents: int = 4
    working_memory: int = 9
    episodic_capacity: int = 4000


class DaedalusConfig(BaseModel):
    run_id: str = "daedalus"
    seed: int = 7
    attention: AttentionConfig = Field(default_factory=AttentionConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    generators: list[str] = Field(default_factory=lambda: [
        "goal", "curiosity", "contradiction", "opportunity", "risk", "reflection"])
    adaptation: bool = True
    metacognition: bool = True
    organization: bool = True
    consolidation: bool = True
    fixed_reflection_period: int | None = None  # baseline only: reflect on a fixed schedule

    @classmethod
    def preset(cls, name: str, seed: int = 7) -> "DaedalusConfig":
        cfg = cls(run_id=name, seed=seed)
        if name == "full":
            return cfg
        if name == "fixed_pipeline":
            cfg.attention.policy = "fixed_pipeline"
            cfg.attention.learning = False
            cfg.adaptation = cfg.metacognition = cfg.organization = False
            cfg.fixed_reflection_period = 20
            return cfg
        if name == "random_attention":
            cfg.attention.policy = "random"
            cfg.attention.learning = False
            return cfg
        if name == "no_curiosity":
            cfg.generators.remove("curiosity")
            return cfg
        if name == "no_reflection":
            cfg.generators.remove("reflection")
            cfg.adaptation = False
            return cfg
        if name == "no_metacognition":
            cfg.metacognition = False
            cfg.adaptation = False
            return cfg
        if name == "no_organization":
            cfg.organization = False
            return cfg
        if name == "no_attention_learning":
            # fixed weights and adaptation, but no learned per-kind bias
            cfg.attention.learning = False
            return cfg
        if name == "with_drives":
            # the same weights, modulated by internal drives (scarcity, fragility,
            # uncertainty, stagnation, failure) rather than held fixed
            cfg.attention.policy = "contextual"
            return cfg
        if name == "no_memory_feedback":
            cfg.attention.memory_feedback = False
            return cfg
        if name == "starvation_bonus":
            cfg.attention.starvation_bonus = 0.35
            return cfg
        if name == "static_weights":
            # nothing about attention changes during the run: no learned bias, no trials
            cfg.attention.learning = False
            cfg.adaptation = False
            return cfg
        raise ValueError(f"unknown preset: {name}")

    PRESETS: ClassVar[tuple[str, ...]] = (
        "full", "fixed_pipeline", "random_attention", "static_weights", "no_attention_learning",
        "with_drives", "no_curiosity", "no_reflection", "no_metacognition", "no_organization",
        "no_memory_feedback", "starvation_bonus")
