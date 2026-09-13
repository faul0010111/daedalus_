"""Graph projections of cognitive state, shaped for the research console."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...cognition.reasoning import information_deficit, position

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def intention_graph(ctx: "CognitiveContext", focal_key: str | None) -> dict[str, Any]:
    nodes, edges, seen = [], [], set()
    for it in sorted(ctx.pool.live.values(), key=lambda i: i.last_score, reverse=True)[:24]:
        nodes.append({"id": it.id, "type": "intention", "label": it.description, "kind": it.kind.value,
                      "score": round(it.last_score, 3), "focal": it.key == focal_key, "status": it.status.value})
        for src in it.sources:
            if src not in seen:
                seen.add(src)
                nodes.append({"id": src, "type": "source", "label": src})
            edges.append({"from": src, "to": it.id, "kind": "proposes"})
        if it.goal_id:
            gid = f"goal:{it.goal_id}"
            if gid not in seen:
                seen.add(gid)
                g = ctx.goals.goals[it.goal_id]
                nodes.append({"id": gid, "type": "goal", "label": g.description, "status": g.status.value})
            edges.append({"from": it.id, "to": gid, "kind": "serves"})
    return {"nodes": nodes, "edges": edges}


def agent_topology(ctx: "CognitiveContext", processes: list[Any]) -> dict[str, Any]:
    nodes = [{"id": "daedalus", "type": "core", "label": "DAEDALUS"}]
    edges = []
    for p in processes:
        nodes.append({"id": p.name, "type": "process", "label": p.name, "period": p.period,
                      "pressure": round(p.last_pressure, 3)})
        edges.append({"from": "daedalus", "to": p.name, "kind": "process"})
    for unit in ctx.agents.units.values():
        uid = unit.name
        nodes.append({"id": uid, "type": "unit", "label": unit.role, "role": unit.role,
                      "contributions": unit.contributions, "created": unit.created_tick,
                      "purpose": unit.purpose_goal})
        edges.append({"from": "daedalus", "to": uid, "kind": "spawned"})
        gid = f"goal:{unit.purpose_goal}"
        if not any(n["id"] == gid for n in nodes):
            nodes.append({"id": gid, "type": "goal", "label": ctx.goals.goals[unit.purpose_goal].description})
        edges.append({"from": uid, "to": gid, "kind": "purpose"})
    return {"nodes": nodes, "edges": edges, "history": ctx.agents.history[-60:]}


def memory_graph(ctx: "CognitiveContext") -> dict[str, Any]:
    nodes, edges = [], []
    items = sorted(ctx.memory.semantic.items.values(), key=lambda k: k.updated_tick, reverse=True)[:30]
    episode_ids: set[str] = set()
    for k in items:
        nodes.append({"id": k.id, "type": k.kind, "label": k.statement, "confidence": round(k.confidence, 3),
                      "support": k.support})
        for eid in k.episodes[-3:]:
            if eid in ctx.memory.episodic.episodes:
                episode_ids.add(eid)
                edges.append({"from": eid, "to": k.id, "kind": "consolidated_into"})
    for eid in episode_ids:
        ep = ctx.memory.episodic.episodes[eid]
        nodes.append({"id": eid, "type": "episode", "label": ep.describe(), "success": ep.success,
                      "tick": ep.tick})
    for (point, variant), stats in ctx.memory.strategic.stats.items():
        sid = f"strategy:{point}:{variant}"
        nodes.append({"id": sid, "type": "strategy", "label": f"{point} = {variant}", "n": stats.n,
                      "mean": round(stats.mean, 4)})
    return {"nodes": nodes, "edges": edges}


def world_view(ctx: "CognitiveContext") -> dict[str, Any]:
    world = ctx.world
    schema = world.schema
    layout = ctx.env.layout()
    here = position(ctx)
    places = world.entities_of_type(schema.explorable_type)
    entities = []
    for place in places:
        hazards = {b.object: round(b.confidence, 3) for b in world.query(place, "hazard", None)}
        contents = [{"item": b.object, "confidence": round(b.confidence, 3), "status": b.status.value}
                    for b in world.query(place, "contains", None, min_conf=0.2)]
        entities.append({
            "id": place, "xy": layout.get(place), "deficit": round(information_deficit(ctx, place), 3),
            "covered": (place, "hazard") in world.coverage, "hazard": hazards, "contains": contents,
            "atrium": world.holds(place, "is_a", "atrium", 0.9), "here": place == here,
            "distance": ctx.distances.get(place),
        })
    edges = set()
    for place in places:
        for other in world.objects(place, schema.edge_predicate, 0.5):
            a, b = sorted((place, other))
            blocked = ctx.env.traversal_blocked(world, a, b)
            edges.add((a, b, blocked))
    return {
        "entities": entities,
        "edges": [{"a": a, "b": b, "blocked": bl} for a, b, bl in sorted(edges)],
        "agent": here,
        "path": ctx.blackboard.get("focal_path", []),
        "trail": ctx.blackboard.get("trail", [])[-60:],
        "holding": world.objects(schema.agent_id, "holding", 0.7),
        "quantities": world.quantities,
        "status_counts": world.status_counts(),
        "uncertainty": round(world.total_uncertainty(), 3),
        "contradictions": [c.to_dict() for c in world.open_contradictions()][-12:],
        "sources": {k: v.to_dict() for k, v in world.sources.items()},
        "hypotheses": [h.to_dict() for h in world.hypotheses.items.values()][-10:],
        "evolution": list(world.evolution)[-240:],
        "beliefs": len(world.beliefs),
    }
