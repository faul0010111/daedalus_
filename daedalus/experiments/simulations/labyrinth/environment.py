"""Labyrinth — a testbed designed to exercise every cognitive pressure.

* Partial observability  -> curiosity (the map and item locations are unknown)
* Locked passages        -> goal emergence (a key becomes a subgoal, its location a knowledge gap)
* Noisy, drifting sensor -> contradictions, source-reliability learning, maintenance opportunities
* Hazards that move      -> risk and validation
* Relics and oil respawn -> opportunities and non-stationarity
* The thread returns     -> persistence: the task never ends, memory should make it cheaper

The environment knows nothing about DAEDALUS' cognition. It only declares
capabilities (tools with preconditions/effects) and emits percepts.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from ....cognition.perception import Observation, Percept
from ....cognition.planning.state import PlanDomain, PlanState
from ....tools import Precondition, ToolSpec
from ....tools.execution import ToolResult
from ....world import WorldModel, WorldSchema
from ..base import Environment

AGENT = "agent"


def item_type(item: str) -> str:
    return {"relic": "treasure", "oil": "fuel", "key": "key"}.get(item.split(":")[0], item)


def door_id(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"door:{x}~{y}"


@dataclass
class LabyrinthConfig:
    width: int = 6
    height: int = 6
    extra_edge_probability: float = 0.2
    hazards: int = 6
    relics: int = 5
    oil: int = 3
    sensor_noise: float = 0.08
    sensor_drift: float = 0.012     # extra noise per scan since last calibration
    sensor_noise_cap: float = 0.42
    dynamics_period: int = 30
    max_energy: float = 100.0
    max_integrity: float = 100.0
    seed: int = 7


class Labyrinth(Environment):
    name = "labyrinth"

    def __init__(self, config: LabyrinthConfig | None = None) -> None:
        self.cfg = config or LabyrinthConfig()
        self.rng = random.Random(self.cfg.seed)
        self.schema = WorldSchema(
            functional={"at", "hazard"},
            inverse_functional={"contains"},
            volatile={"contains": 0.0015, "hazard": 0.006},
            priors={"contains": 0.25, "hazard": 0.34, "locked": 0.1, "connected": 0.1, "holding": 0.1,
                    "deposited": 0.05, "is_a": 0.5, "value": 0.5},
            epistemic={"contains", "hazard"},
            fluents={"at", "holding", "contains", "locked", "deposited"},
            explorable_type="location", agent_id=AGENT, position_predicate="at", edge_predicate="connected",
        )
        self._generate()
        self.tick = 0
        self.events: deque[dict[str, Any]] = deque(maxlen=300)
        self.stats = {"threads_recovered": 0, "relic_value_banked": 0.0, "collapses": 0,
                      "exhausted_ticks": 0, "damage_taken": 0.0, "scans": 0, "calibrations": 0,
                      "relics_lost": 0}
        self.first_thread_tick: int | None = None
        self.thread_ticks: list[int] = []
        self._pending_signals: list[Observation] = []

    # ================================================================ generation
    def _generate(self) -> None:
        w, h, rng = self.cfg.width, self.cfg.height, self.rng
        self.rooms = [f"r{x}_{y}" for y in range(h) for x in range(w)]
        self.atrium = "r0_0"
        coords = {f"r{x}_{y}": (x, y) for y in range(h) for x in range(w)}

        def grid_neighbors(r: str) -> list[str]:
            x, y = coords[r]
            out = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    out.append(f"r{nx}_{ny}")
            return out

        # randomized DFS spanning tree
        tree: dict[str, set[str]] = {r: set() for r in self.rooms}
        visited, stack = {self.atrium}, [self.atrium]
        while stack:
            cur = stack[-1]
            options = [n for n in grid_neighbors(cur) if n not in visited]
            if not options:
                stack.pop()
                continue
            nxt = rng.choice(options)
            tree[cur].add(nxt)
            tree[nxt].add(cur)
            visited.add(nxt)
            stack.append(nxt)

        dist, parent = self._bfs(tree, self.atrium)
        self.thread_room = max(self.rooms, key=lambda r: (dist[r], r))
        path = [self.thread_room]
        while path[-1] != self.atrium:
            path.append(parent[path[-1]])
        path.reverse()
        lock_a, lock_b = path[-3], path[-2]
        vault = self._component(tree, lock_b, blocked=(lock_a, lock_b))
        self.adjacency = {r: set(ns) for r, ns in tree.items()}

        # silver-locked side chamber: a leaf outside the vault, holding the richest relic
        leaves = [r for r in self.rooms if len(tree[r]) == 1 and r not in vault and r != self.atrium
                  and dist[r] >= 3]
        self.side_chamber = rng.choice(leaves) if leaves else None
        forbidden = set(vault) | ({self.side_chamber} if self.side_chamber else set())
        for r in self.rooms:
            for n in grid_neighbors(r):
                if n in self.adjacency[r] or r > n:
                    continue
                same_side = (r in vault) == (n in vault)
                if same_side and r not in forbidden - set(vault) and n not in forbidden - set(vault) \
                        and rng.random() < self.cfg.extra_edge_probability:
                    if self.side_chamber in (r, n):
                        continue
                    self.adjacency[r].add(n)
                    self.adjacency[n].add(r)

        self.locks: dict[str, str] = {door_id(lock_a, lock_b): "gold"}
        self.vault = vault
        if self.side_chamber:
            (only,) = tuple(tree[self.side_chamber])
            self.locks[door_id(self.side_chamber, only)] = "silver"
        self.ever_locked = dict(self.locks)

        outside = [r for r in self.rooms if r not in vault and r != self.atrium and r != self.side_chamber]
        far_outside = [r for r in outside if dist[r] >= 3] or outside
        self.items: dict[str, str] = {}   # item -> room
        self.values: dict[str, int] = {}
        self.items["thread"] = self.thread_room
        self.values["thread"] = 10
        gold_room = rng.choice(far_outside)
        self.items["key:gold"] = gold_room
        self.items["key:silver"] = rng.choice([r for r in outside if r != gold_room] or outside)
        self._relic_seq = 0
        if self.side_chamber:
            self._spawn_relic(self.side_chamber, value=5)
        for _ in range(self.cfg.relics):
            self._spawn_relic(rng.choice(outside + list(vault)))
        self._oil_seq = 0
        for _ in range(self.cfg.oil):
            self._spawn_oil()
        candidates = [r for r in self.rooms if r != self.atrium]
        self.hazard: dict[str, str] = {}
        for r in rng.sample(candidates, self.cfg.hazards):
            self.hazard[r] = "high" if rng.random() < 0.45 else "low"

        self.agent_room = self.atrium
        self.energy = self.cfg.max_energy
        self.integrity = self.cfg.max_integrity
        self.holding: set[str] = set()
        self.scans_since_calibration = 0
        self.epoch = 1

    @staticmethod
    def _bfs(adj: dict[str, set[str]], start: str) -> tuple[dict[str, int], dict[str, str]]:
        dist, parent, q = {start: 0}, {}, deque([start])
        while q:
            cur = q.popleft()
            for n in sorted(adj[cur]):
                if n not in dist:
                    dist[n], parent[n] = dist[cur] + 1, cur
                    q.append(n)
        return dist, parent

    @staticmethod
    def _component(adj: dict[str, set[str]], start: str, blocked: tuple[str, str]) -> set[str]:
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            for n in sorted(adj[cur]):
                if {cur, n} == set(blocked) or n in seen:
                    continue
                seen.add(n)
                stack.append(n)
        return seen

    def _spawn_relic(self, room: str, value: int | None = None) -> str:
        self._relic_seq += 1
        item = f"relic:{self._relic_seq}"
        self.items[item] = room
        self.values[item] = value if value is not None else self.rng.choice((1, 2, 2, 3))
        return item

    def _spawn_oil(self) -> str:
        self._oil_seq += 1
        item = f"oil:{self._oil_seq}"
        room = self.rng.choice([r for r in self.rooms if r != self.atrium and r not in self.vault])
        self.items[item] = room
        return item

    # ================================================================ environment port
    def sources(self) -> dict[str, float]:
        return {"proprioception": 0.999, "glance": 0.92, "scan": 0.88, "probe": 0.99, "touch": 0.99,
                "pain": 0.95}

    def initial_goals(self) -> list[dict[str, Any]]:
        return [
            {"description": "Return the Thread of Ariadne to the Atrium", "kind": "achieve",
             "pattern": ("thread", "deposited", "yes"), "importance": 0.9, "persistent": True},
            {"description": "Keep energy above 30", "kind": "maintain", "quantity": "energy",
             "threshold": 30.0, "comfort": 70.0, "importance": 0.85},
            {"description": "Keep structural integrity above 45", "kind": "maintain", "quantity": "integrity",
             "threshold": 45.0, "comfort": 80.0, "importance": 0.75},
        ]

    def _noise(self) -> float:
        return min(self.cfg.sensor_noise_cap,
                   self.cfg.sensor_noise + self.cfg.sensor_drift * self.scans_since_calibration)

    def sense(self) -> Percept:
        room = self.agent_room
        obs = [Observation(AGENT, "at", room, True, 0.999, "proprioception"),
               Observation(room, "is_a", "location", True, 0.999, "proprioception")]
        if room == self.atrium:
            obs.append(Observation(room, "is_a", "atrium", True, 0.999, "proprioception"))
        for n in sorted(self.adjacency[room]):
            obs.append(Observation(room, "connected", n, True, 0.99, "proprioception"))
            obs.append(Observation(n, "connected", room, True, 0.99, "proprioception"))
            obs.append(Observation(n, "is_a", "location", True, 0.99, "proprioception"))
            d = door_id(room, n)
            if d in self.ever_locked:
                color = self.ever_locked[d]
                obs.append(Observation(d, "locked", color, d in self.locks, 0.98, "proprioception"))
        for item, where in self.items.items():
            if where == room:
                obs.append(Observation(room, "contains", item, True, 0.92, "glance"))
                obs.append(Observation(item, "is_a", item_type(item), True, 0.99, "glance"))
                if item in self.values:
                    obs.append(Observation(item, "value", str(self.values[item]), True, 0.99, "glance"))
        for item in sorted(self.holding):
            obs.append(Observation(AGENT, "holding", item, True, 0.999, "proprioception"))
        obs.extend(self._pending_signals)
        self._pending_signals = []
        return Percept(
            observations=obs,
            coverage=[(room, "contains", 0.92, "glance"), (AGENT, "holding", 0.999, "proprioception")],
            quantities=self._quantities(),
        )

    def _quantities(self) -> dict[str, float]:
        carried = sum(self.values.get(i, 0) for i in sorted(self.holding) if i.startswith("relic"))
        return {"energy": round(self.energy, 2), "integrity": round(self.integrity, 2),
                "carried_value": carried, "banked_value": self.stats["relic_value_banked"],
                "threads_recovered": self.stats["threads_recovered"]}

    def _spend(self, cost: float) -> bool:
        if self.energy < cost:
            self.stats["exhausted_ticks"] += 1
            return False
        self.energy -= cost
        return True

    async def execute(self, tool: str, args: dict[str, Any]) -> ToolResult:
        handler = getattr(self, f"_do_{tool}", None)
        if handler is None:
            return ToolResult(tool, args, False, reason="unknown_tool")
        spec_cost = {"move": 1, "scan": 2, "probe": 3, "take": 1, "unlock": 1, "deposit": 0, "consume": 0,
                     "rest": 0, "calibrate": 4}[tool]
        if not self._spend(spec_cost):
            return ToolResult(tool, args, False, Percept(quantities=self._quantities()), reason="exhausted")
        result: ToolResult = handler(args)
        result.energy_spent = spec_cost
        result.percept.quantities = self._quantities()
        return result

    # ---------------------------------------------------------------- actions
    def _do_move(self, args: dict[str, Any]) -> ToolResult:
        to, room = args.get("to"), self.agent_room
        if to not in self.adjacency[room]:
            return ToolResult("move", args, False, Percept(), reason="not_adjacent")
        d = door_id(room, to)
        if d in self.locks:
            return ToolResult("move", args, False, Percept(
                [Observation(d, "locked", self.locks[d], True, 0.99, "touch")]), reason="locked")
        self.agent_room = to
        obs: list[Observation] = [Observation(AGENT, "at", to, True, 0.999, "proprioception")]
        damage = 0.0
        level = self.hazard.get(to)
        if level:
            chance, dmg = (0.45, 18.0) if level == "high" else (0.18, 6.0)
            if self.rng.random() < chance:
                damage = dmg
                self.integrity -= dmg
                self.stats["damage_taken"] += dmg
                obs.append(Observation(to, "hazard", level, True, 0.95, "pain"))
        result = ToolResult("move", args, True, Percept(obs), damage=damage)
        if self.integrity <= 0:
            lost = sorted(i for i in self.holding if i.startswith("relic"))
            for i in lost:
                # a carried item is not on any floor: it left self.items when it was taken
                self.holding.discard(i)
                self.values.pop(i, None)
                self.stats["relics_lost"] += 1
                self._spawn_relic(self.rng.choice([r for r in self.rooms if r != self.atrium]))
            self.stats["collapses"] += 1
            self.agent_room = self.atrium
            self.integrity = 60.0
            result.info["collapse"] = True
            result.reason = "collapsed"
        return result

    def _scan_room(self, room: str, noise: float, source: str) -> tuple[list[Observation], list]:
        obs: list[Observation] = []
        present = [i for i, r in self.items.items() if r == room]
        claimed = 1.0 - noise if source == "scan" else 0.99
        for item in present:
            if self.rng.random() >= noise:
                obs.append(Observation(room, "contains", item, True, claimed if source == "scan" else 0.99, source))
                obs.append(Observation(item, "is_a", item_type(item), True, 0.99, source))
                if item in self.values:
                    obs.append(Observation(item, "value", str(self.values[item]), True, 0.99, source))
        if source == "scan" and self.rng.random() < noise * 0.6:
            elsewhere = [i for i, r in self.items.items() if r != room and not i.startswith("oil")]
            if elsewhere:
                obs.append(Observation(room, "contains", self.rng.choice(elsewhere), True, claimed, source))
        truth = self.hazard.get(room, "none")
        reading = truth
        if source == "scan" and self.rng.random() < noise:
            reading = self.rng.choice([lv for lv in ("none", "low", "high") if lv != truth])
        obs.append(Observation(room, "hazard", reading, True, claimed if source == "scan" else 0.99, source))
        rel = self.sources()[source]
        coverage = [(room, "contains", rel, source), (room, "hazard", rel, source)]
        return obs, coverage

    def _do_scan(self, args: dict[str, Any]) -> ToolResult:
        noise = self._noise()
        self.scans_since_calibration += 1
        self.stats["scans"] += 1
        percept = Percept()
        for room in [self.agent_room, *sorted(self.adjacency[self.agent_room])]:
            obs, cov = self._scan_room(room, noise if room != self.agent_room else noise / 3, "scan")
            percept.observations.extend(obs)
            percept.coverage.extend(cov)
        return ToolResult("scan", args, True, percept, info={"rooms": 1 + len(self.adjacency[self.agent_room])})

    def _do_probe(self, args: dict[str, Any]) -> ToolResult:
        room = args.get("room")
        if room != self.agent_room and room not in self.adjacency[self.agent_room]:
            return ToolResult("probe", args, False, reason="out_of_reach")
        obs, cov = self._scan_room(room, 0.0, "probe")
        return ToolResult("probe", args, True, Percept(obs, cov))

    def _do_take(self, args: dict[str, Any]) -> ToolResult:
        item, room = args.get("item"), self.agent_room
        if self.items.get(item) != room:
            return ToolResult("take", args, False, Percept(
                [Observation(room, "contains", item, False, 0.99, "touch")]), reason="not_present")
        del self.items[item]
        self.holding.add(item)
        return ToolResult("take", args, True, Percept([
            Observation(AGENT, "holding", item, True, 0.999, "touch"),
            Observation(room, "contains", item, False, 0.999, "touch")]))

    def _do_unlock(self, args: dict[str, Any]) -> ToolResult:
        d = args.get("door")
        color = self.locks.get(d)
        rooms = d.removeprefix("door:").split("~") if d else []
        if self.agent_room not in rooms:
            return ToolResult("unlock", args, False, reason="not_at_door")
        if color is None:
            return ToolResult("unlock", args, False, Percept(
                [Observation(d, "locked", self.ever_locked.get(d, "gold"), False, 0.99, "touch")]),
                reason="not_locked")
        key = f"key:{color}"
        if key not in self.holding:
            return ToolResult("unlock", args, False, reason="missing_key")
        del self.locks[d]
        self.holding.discard(key)
        return ToolResult("unlock", args, True, Percept([
            Observation(d, "locked", color, False, 0.999, "touch"),
            Observation(AGENT, "holding", key, False, 0.999, "touch")]))

    def _do_deposit(self, args: dict[str, Any]) -> ToolResult:
        item = args.get("item")
        if self.agent_room != self.atrium:
            return ToolResult("deposit", args, False, reason="not_at_atrium")
        if item not in self.holding:
            return ToolResult("deposit", args, False, Percept(
                [Observation(AGENT, "holding", item, False, 0.999, "touch")]), reason="not_holding")
        self.holding.discard(item)
        obs = [Observation(item, "deposited", "yes", True, 0.999, "touch"),
               Observation(AGENT, "holding", item, False, 0.999, "touch")]
        if item == "thread":
            self.stats["threads_recovered"] += 1
            self.thread_ticks.append(self.tick)
            self.first_thread_tick = self.first_thread_tick or self.tick
            self._new_epoch()
        else:
            self.stats["relic_value_banked"] += self.values.get(item, 0)
        return ToolResult("deposit", args, True, Percept(obs))

    def _new_epoch(self) -> None:
        self.epoch += 1
        dist, _ = self._bfs(self.adjacency, self.atrium)
        far = sorted(self.rooms, key=lambda r: dist.get(r, 0))[len(self.rooms) // 2:]
        room = self.rng.choice(far)
        self.items["thread"] = room
        # the thread slips back into the labyrinth: the agent notices on the next percept
        self._pending_signals.append(Observation("thread", "deposited", "yes", False, 0.999, "proprioception"))
        self.events.append({"tick": self.tick, "event": "epoch", "epoch": self.epoch, "thread_room": room})

    def _do_consume(self, args: dict[str, Any]) -> ToolResult:
        item = args.get("item")
        if item not in self.holding or not str(item).startswith("oil"):
            return ToolResult("consume", args, False, reason="not_holding")
        self.holding.discard(item)
        self.energy = min(self.cfg.max_energy, self.energy + 45)
        return ToolResult("consume", args, True, Percept([Observation(AGENT, "holding", item, False, 0.999, "touch")]))

    def _do_rest(self, args: dict[str, Any]) -> ToolResult:
        self.energy = min(self.cfg.max_energy, self.energy + 3)
        self.integrity = min(self.cfg.max_integrity, self.integrity + 2)
        return ToolResult("rest", args, True)

    def _do_calibrate(self, args: dict[str, Any]) -> ToolResult:
        self.scans_since_calibration = 0
        self.stats["calibrations"] += 1
        return ToolResult("calibrate", args, True)

    # ---------------------------------------------------------------- dynamics
    def advance(self, tick: int) -> list[dict[str, Any]]:
        self.tick = tick
        changes: list[dict[str, Any]] = []
        if tick % self.cfg.dynamics_period != 0:
            return changes
        if self.hazard:
            src = self.rng.choice(sorted(self.hazard))
            options = [n for n in self.adjacency[src] if n != self.atrium and n not in self.hazard]
            if options:
                dst = self.rng.choice(sorted(options))
                self.hazard[dst] = self.hazard.pop(src)
                changes.append({"event": "hazard_shift", "from": src, "to": dst, "level": self.hazard[dst]})
        relics_on_floor = sum(1 for i in self.items if i.startswith("relic"))
        if relics_on_floor < self.cfg.relics + 1:
            room = self.rng.choice([r for r in self.rooms if r != self.atrium])
            item = self._spawn_relic(room)
            changes.append({"event": "relic_spawn", "item": item, "room": room, "value": self.values[item]})
        if sum(1 for i in self.items if i.startswith("oil")) < 2:
            item = self._spawn_oil()
            changes.append({"event": "oil_spawn", "item": item, "room": self.items[item]})
        for c in changes:
            self.events.append({"tick": tick, **c})
        return changes

    def traversal_blocked(self, world: WorldModel, a: str, b: str) -> bool:
        return any(bl.confidence >= 0.5 for bl in world.query(door_id(a, b), "locked", None))

    # ---------------------------------------------------------------- observability
    def ground_truth(self) -> dict[str, Any]:
        return {
            "width": self.cfg.width, "height": self.cfg.height, "atrium": self.atrium,
            "agent": self.agent_room, "epoch": self.epoch,
            "edges": sorted({tuple(sorted((a, b))) for a, ns in self.adjacency.items() for b in ns}),
            "locks": self.locks, "items": self.items, "values": self.values, "hazards": self.hazard,
            "holding": sorted(self.holding), "energy": self.energy, "integrity": self.integrity,
            "sensor_noise": round(self._noise(), 3), "vault": sorted(self.vault),
            "events": list(self.events)[-20:],
        }

    def layout(self) -> dict[str, tuple[float, float]]:
        return {r: (float(r[1:].split("_")[0]), float(r[1:].split("_")[1])) for r in self.rooms}

    def task_metrics(self) -> dict[str, float]:
        return {**self.stats, "first_thread_tick": self.first_thread_tick or -1,
                "epoch": self.epoch, "energy": self.energy, "integrity": self.integrity}

    def to_dict(self) -> dict[str, Any]:
        return {"cfg": asdict(self.cfg), "rng": self.rng.getstate(), "adjacency": {k: sorted(v) for k, v in self.adjacency.items()},
                "locks": self.locks, "ever_locked": self.ever_locked, "items": self.items, "values": self.values,
                "hazard": self.hazard, "agent_room": self.agent_room, "energy": self.energy,
                "integrity": self.integrity, "holding": sorted(self.holding), "scans": self.scans_since_calibration,
                "epoch": self.epoch, "stats": self.stats, "tick": self.tick, "relic_seq": self._relic_seq,
                "oil_seq": self._oil_seq, "vault": sorted(self.vault), "first_thread_tick": self.first_thread_tick,
                "thread_ticks": self.thread_ticks}

    def load_dict(self, d: dict[str, Any]) -> None:
        state = d["rng"]
        self.rng.setstate((state[0], tuple(state[1]), state[2]))
        self.adjacency = {k: set(v) for k, v in d["adjacency"].items()}
        self.locks, self.ever_locked = d["locks"], d["ever_locked"]
        self.items, self.values, self.hazard = d["items"], d["values"], d["hazard"]
        self.agent_room, self.energy, self.integrity = d["agent_room"], d["energy"], d["integrity"]
        self.holding, self.scans_since_calibration = set(d["holding"]), d["scans"]
        self.epoch, self.stats, self.tick = d["epoch"], d["stats"], d["tick"]
        self._relic_seq, self._oil_seq, self.vault = d["relic_seq"], d["oil_seq"], set(d["vault"])
        self.first_thread_tick, self.thread_ticks = d["first_thread_tick"], d["thread_ticks"]

    # ================================================================ capabilities
    def capabilities(self) -> list[ToolSpec]:
        atrium_type = "atrium"

        def pos(state: PlanState) -> str | None:
            at = state.objects(AGENT, "at")
            return at[0] if at else None

        def move_ground(state: PlanState, domain: PlanDomain):
            here = pos(state)
            if here:
                for n in domain.objects(here, "connected"):
                    yield {"from": here, "to": n}

        def move_check(state: PlanState, args, domain: PlanDomain) -> list[Precondition]:
            unmet = []
            for color in state.objects(door_id(args["from"], args["to"]), "locked"):
                key = f"key:{color}"
                if state.has(AGENT, "holding", key):
                    unmet.append(Precondition((door_id(args["from"], args["to"]), "locked", color), False, False))
                else:
                    unmet.append(Precondition((AGENT, "holding", key), True, relaxable=True))
            return unmet

        def move_apply(state: PlanState, args, domain) -> PlanState:
            return state.with_changes([(AGENT, "at", args["to"])], [(AGENT, "at", args["from"])])

        def move_cost(state: PlanState, args, domain: PlanDomain) -> float:
            to = args["to"]
            return 1.0 + 7.0 * domain.conf(to, "hazard", "high", 0.0) + 1.5 * domain.conf(to, "hazard", "low", 0.0)

        def move_support(state, args, domain):
            return [(args["from"], "connected", args["to"])]

        def take_ground(state: PlanState, domain: PlanDomain):
            here = pos(state)
            if here:
                for item in state.objects(here, "contains"):
                    if item in domain.relevant:
                        yield {"item": item, "room": here}

        def take_apply(state, args, domain):
            return state.with_changes([(AGENT, "holding", args["item"])], [(args["room"], "contains", args["item"])])

        def unlock_ground(state: PlanState, domain: PlanDomain):
            here = pos(state)
            if here:
                for n in domain.objects(here, "connected"):
                    d = door_id(here, n)
                    for color in state.objects(d, "locked"):
                        yield {"door": d, "color": color}

        def unlock_check(state: PlanState, args, domain) -> list[Precondition]:
            key = f"key:{args['color']}"
            return [] if state.has(AGENT, "holding", key) else [Precondition((AGENT, "holding", key))]

        def unlock_apply(state, args, domain):
            return state.with_changes([], [(args["door"], "locked", args["color"]),
                                           (AGENT, "holding", f"key:{args['color']}")])

        def unlock_instrumental(domain: PlanDomain) -> set[str]:
            return {f"key:{f[2]}" for f in domain.initial.where("locked")}

        def deposit_ground(state: PlanState, domain: PlanDomain):
            here = pos(state)
            if here and domain.static(here, "is_a", atrium_type):
                for item in state.objects(AGENT, "holding"):
                    if item == "thread" or item.startswith("relic"):
                        yield {"item": item}

        def deposit_apply(state, args, domain):
            return state.with_changes([(args["item"], "deposited", "yes")], [(AGENT, "holding", args["item"])])

        def consume_ground(state: PlanState, domain):
            for item in state.objects(AGENT, "holding"):
                if item.startswith("oil"):
                    yield {"item": item}

        def consume_apply(state, args, domain):
            return state.with_changes([], [(AGENT, "holding", args["item"])])

        return [
            ToolSpec("move", "Walk through an open passage to an adjacent chamber.", "action", ["to"], 1,
                     ground=move_ground, check=move_check, apply=move_apply, step_cost=move_cost,
                     support=move_support, requires=lambda b: []),
            ToolSpec("take", "Pick up an item in the current chamber.", "action", ["item"], 1,
                     ground=take_ground, apply=take_apply,
                     support=lambda st, a, d: [(a["room"], "contains", a["item"])],
                     produces=(AGENT, "holding", "?item"),
                     knowledge=lambda b: [("?room", "contains", b.get("?item", "?item"))]),
            ToolSpec("unlock", "Open a locked passage with a key of matching colour (consumes the key).",
                     "action", ["door"], 1, ground=unlock_ground, check=unlock_check, apply=unlock_apply,
                     instrumental=unlock_instrumental),
            ToolSpec("deposit", "Leave a carried relic or the thread in the Atrium.", "action", ["item"], 0,
                     ground=deposit_ground, apply=deposit_apply,
                     produces=("?item", "deposited", "yes"),
                     requires=lambda b: [(AGENT, "holding", b["?item"])] if "?item" in b else [],
                     knowledge=lambda b: [("?place", "is_a", atrium_type)]),
            ToolSpec("consume", "Burn a carried oil flask to restore energy.", "maintenance", ["item"], 0,
                     ground=consume_ground, apply=consume_apply, restores={"energy": 45},
                     consumes_type="fuel"),
            ToolSpec("rest", "Stay still; recovers a little energy and integrity.", "maintenance", [], 0,
                     ground=lambda st, d: iter([{}]), apply=lambda st, a, d: st,
                     restores={"energy": 3, "integrity": 2}),
            ToolSpec("scan", "Sense the current and adjacent chambers (cheap, noisy, drifts with use).",
                     "epistemic", [], 2, reveals={"contains", "hazard"}, reach=1),
            ToolSpec("probe", "Examine one chamber in reach precisely (expensive, reliable).",
                     "epistemic", ["room"], 3, reveals={"contains", "hazard"}, reach=1),
            ToolSpec("calibrate", "Recalibrate the scanner, removing accumulated drift.", "maintenance", [], 4,
                     maintains="scan"),
        ]
