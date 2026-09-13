"""The persistent, probabilistic model of the environment.

Every element carries a confidence and an epistemic status. Evidence from
different sources is accumulated in log-odds space, weighted by a *learned*
estimate of each source's reliability (learning happens in the reflection
engine; the world model only keeps the verification ledger).
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, Iterable

from ..beliefs import Belief, EpistemicStatus, Evidence, binary_entropy, update
from ..contradictions import Contradiction
from ..hypotheses import HypothesisRegistry
from .schema import Fact, WorldSchema

if TYPE_CHECKING:
    from ...core.events import EventBus

WILDCARD = "?"


def is_var(term: str) -> bool:
    return term.startswith("?")


class SourceReliability:
    """Beta posterior over how often a source's claims survive verification."""

    def __init__(self, nominal: float, strength: float = 8.0) -> None:
        self.nominal = nominal
        self.alpha = nominal * strength
        self.beta = (1 - nominal) * strength
        self.verified = 0
        self.refuted = 0

    @property
    def estimate(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def record(self, correct: bool, forgetting: float = 0.96) -> None:
        # exponential forgetting keeps the estimate responsive to drift and repair
        prior_a, prior_b = self.nominal * 2.0, (1 - self.nominal) * 2.0
        self.alpha = prior_a + (self.alpha - prior_a) * forgetting
        self.beta = prior_b + (self.beta - prior_b) * forgetting
        if correct:
            self.alpha += 1
            self.verified += 1
        else:
            self.beta += 1
            self.refuted += 1

    def to_dict(self) -> dict[str, Any]:
        return {"nominal": round(self.nominal, 3), "estimate": round(self.estimate, 3),
                "verified": self.verified, "refuted": self.refuted}


class ObservationResult:
    __slots__ = ("belief", "created", "entropy_delta", "contradiction", "resolved", "prior")

    def __init__(self, belief: Belief, created: bool, entropy_delta: float, prior: float,
                 contradiction: Contradiction | None, resolved: Contradiction | None) -> None:
        self.belief = belief
        self.created = created
        self.entropy_delta = entropy_delta
        self.prior = prior
        self.contradiction = contradiction
        self.resolved = resolved


class WorldModel:
    def __init__(self, schema: WorldSchema, bus: "EventBus | None" = None,
                 tick_provider=lambda: 0) -> None:
        self.schema = schema
        self.bus = bus
        self._tick = tick_provider
        self.beliefs: dict[Fact, Belief] = {}
        self._by_subject: dict[str, set[Fact]] = defaultdict(set)
        self._by_predicate: dict[str, set[Fact]] = defaultdict(set)
        self._by_object: dict[str, set[Fact]] = defaultdict(set)
        self.contradictions: dict[str, Contradiction] = {}
        self._open_contradiction_by_key: dict[Fact, str] = {}
        self.hypotheses = HypothesisRegistry()
        self.sources: dict[str, SourceReliability] = {}
        self.verification_ledger: deque[dict[str, Any]] = deque(maxlen=400)
        self.coverage: dict[tuple[str, str], tuple[int, int]] = {}  # (entity, predicate) -> (count, last tick)
        self.quantities: dict[str, float] = {}
        self.quantity_history: dict[str, deque[tuple[int, float]]] = defaultdict(lambda: deque(maxlen=300))
        self.critical: dict[Fact, int] = {}
        self.revision = 0
        self.structural_revision = 0
        self.evolution: deque[dict[str, Any]] = deque(maxlen=600)
        self.cumulative_uncertainty_reduction = 0.0
        self._cseq = 0

    # ------------------------------------------------------------------ sources
    def register_source(self, name: str, nominal: float) -> None:
        if name not in self.sources:
            self.sources[name] = SourceReliability(nominal)

    def effective_reliability(self, source: str, reliability: float) -> float:
        src = self.sources.get(source)
        if src is None:
            return reliability
        # nominal reliability is a claim; the posterior is what the agent has learned
        return min(reliability, src.estimate) if src.verified + src.refuted > 0 else reliability

    # ---------------------------------------------------------------- mutation
    def _index(self, key: Fact) -> None:
        s, p, o = key
        self._by_subject[s].add(key)
        self._by_predicate[p].add(key)
        self._by_object[o].add(key)

    def _status(self, b: Belief) -> EpistemicStatus:
        if b.contradiction_open:
            return EpistemicStatus.CONTRADICTED
        last = b.evidence[-1] if b.evidence else None
        if last and last.source == "hypothesis":
            return EpistemicStatus.HYPOTHESIS
        strong = any(e.reliability >= 0.95 and not e.source.startswith("inference") for e in b.evidence[-3:])
        if strong and (b.confidence >= 0.9 or b.confidence <= 0.1):
            return EpistemicStatus.OBSERVED_FACT
        if 0.3 <= b.confidence <= 0.7:
            return EpistemicStatus.UNCERTAIN
        return EpistemicStatus.INFERRED_BELIEF

    def observe(self, s: str, p: str, o: str, positive: bool = True, reliability: float = 0.9,
                source: str = "perception", _propagate: bool = True) -> ObservationResult:
        tick = self._tick()
        key = (s, p, o)
        belief = self.beliefs.get(key)
        created = belief is None
        if created:
            prior = self.schema.prior(p)
            belief = Belief(s, p, o, prior, prior, EpistemicStatus.UNCERTAIN, tick, tick)
            self.beliefs[key] = belief
            self._index(key)
            if p not in self.schema.fluents and p not in self.schema.volatile:
                self.structural_revision += 1
        r = self.effective_reliability(source, reliability)
        before = belief.confidence
        h_before = binary_entropy(before)
        belief.confidence = update(before, positive, r)
        belief.evidence.append(Evidence(source, tick, positive, r))
        if len(belief.evidence) > 12:
            del belief.evidence[0]
        belief.updated_tick = tick
        if not belief.history or belief.history[-1][1] != round(belief.confidence, 3):
            belief.history.append((tick, round(belief.confidence, 3)))
            if len(belief.history) > 40:
                del belief.history[0]

        contradiction = resolved = None
        direct = not source.startswith("inference")
        # a confident belief meeting credible opposing evidence is a contradiction
        if direct and not created and r >= 0.85 and (
            (positive and before <= 0.15) or (not positive and before >= 0.85)
        ) and not belief.contradiction_open:
            self._cseq += 1
            contradiction = Contradiction(f"c{self._cseq}", key, tick, before, belief.confidence,
                                          source, severity=abs(before - (1.0 if positive else 0.0)) * r)
            self.contradictions[contradiction.id] = contradiction
            self._open_contradiction_by_key[key] = contradiction.id
            belief.contradiction_open = True
        elif belief.contradiction_open and direct and r >= 0.95:
            cid = self._open_contradiction_by_key.pop(key, None)
            if cid:
                resolved = self.contradictions[cid]
                resolved.resolved_tick = tick
                resolved.resolution = f"verified by {source}: {'true' if positive else 'false'}"
            belief.contradiction_open = False

        # verification ledger: strong direct evidence grades earlier noisy claims
        if direct and r >= 0.95 and not created:
            truth = positive
            for ev in belief.evidence[:-1]:
                if ev.source != source and not ev.source.startswith("inference") and ev.reliability < 0.95 \
                        and tick - ev.tick <= 120:
                    self.verification_ledger.append(
                        {"tick": tick, "source": ev.source, "claimed": ev.positive, "truth": truth,
                         "predicate": p, "age": tick - ev.tick})

        belief.status = self._status(belief)
        delta = h_before - belief.entropy
        if delta > 0:
            self.cumulative_uncertainty_reduction += delta
        self.revision += 1

        if self.bus is not None:
            from ...core.events import EventType
            if created:
                self.bus.publish(EventType.BELIEF_CREATED, "world_model",
                                 {"key": list(key), "confidence": round(belief.confidence, 3),
                                  "status": belief.status.value, "source": source})
            elif abs(belief.confidence - before) >= 0.25:
                self.bus.publish(EventType.BELIEF_REVISED, "world_model",
                                 {"key": list(key), "from": round(before, 3),
                                  "to": round(belief.confidence, 3), "status": belief.status.value,
                                  "source": source})
            if contradiction:
                self.bus.publish(EventType.CONTRADICTION, "world_model", contradiction.to_dict())
            if resolved:
                self.bus.publish(EventType.CONTRADICTION_RESOLVED, "world_model", resolved.to_dict())

        if _propagate and positive and belief.confidence > 0.6:
            self._propagate_exclusivity(belief, r)
        return ObservationResult(belief, created, delta, before, contradiction, resolved)

    def _propagate_exclusivity(self, belief: Belief, reliability: float) -> None:
        """Enforce the probability constraint a functional predicate implies.

        If `agent at r2` holds with confidence c, then `agent at r1` can be no
        more likely than 1 - c. This is a constraint, not another piece of
        evidence, so it is applied as a cap rather than an update.
        """
        s, p, o = belief.key
        cap = min(0.97, max(0.01, 1.0 - belief.confidence))
        pairs: list[tuple[Fact, ...]] = []
        if p in self.schema.functional:
            pairs.append(tuple(k for k in sorted(self._by_subject.get(s, ())) if k[1] == p and k[2] != o))
        if p in self.schema.inverse_functional:
            pairs.append(tuple(k for k in sorted(self._by_object.get(o, ())) if k[1] == p and k[0] != s))
        tick = self._tick()
        for group in pairs:
            for key in group:
                other = self.beliefs[key]
                if other.confidence <= cap:
                    continue
                before = other.confidence
                other.confidence = cap
                other.evidence.append(Evidence("inference:exclusivity", tick, False, reliability))
                del other.evidence[:-12]
                other.updated_tick = tick
                other.rationale = f"excluded by {' '.join(belief.key)}"
                other.status = self._status(other)
                if not other.history or other.history[-1][1] != round(other.confidence, 3):
                    other.history.append((tick, round(other.confidence, 3)))
                    del other.history[:-40]
                if self.bus is not None and abs(before - cap) >= 0.25:
                    from ...core.events import EventType
                    self.bus.publish(EventType.BELIEF_REVISED, "world_model",
                                     {"key": list(key), "from": round(before, 3), "to": round(cap, 3),
                                      "status": other.status.value, "source": "inference:exclusivity"})

    def infer(self, s: str, p: str, o: str, positive: bool, reliability: float, rationale: str) -> Belief:
        res = self.observe(s, p, o, positive, reliability, source="inference:reasoning")
        res.belief.rationale = rationale
        return res.belief

    def hypothesize(self, s: str, p: str, o: str, confidence: float, statement: str, origin: str,
                    test: str) -> Any:
        key = (s, p, o)
        tick = self._tick()
        if key not in self.beliefs:
            b = Belief(s, p, o, confidence, 0.5, EpistemicStatus.HYPOTHESIS, tick, tick,
                       evidence=[Evidence("hypothesis", tick, True, confidence)], rationale=statement)
            self.beliefs[key] = b
            self._index(key)
        h = self.hypotheses.form(statement, key, tick, origin, test)
        if self.bus is not None and h.support == 0 and h.refutations == 0 and h.formed_tick == tick:
            from ...core.events import EventType
            self.bus.publish(EventType.HYPOTHESIS, origin, h.to_dict())
        return h

    def cover(self, entity: str, predicate: str) -> None:
        count, _ = self.coverage.get((entity, predicate), (0, 0))
        self.coverage[(entity, predicate)] = (count + 1, self._tick())

    def set_quantity(self, name: str, value: float) -> None:
        self.quantities[name] = value
        hist = self.quantity_history[name]
        if not hist or hist[-1][1] != value:
            hist.append((self._tick(), value))

    def mark_critical(self, keys: Iterable[Fact]) -> None:
        tick = self._tick()
        for k in keys:
            self.critical[k] = tick

    def decay(self) -> None:
        """Volatile beliefs drift toward their prior when not re-observed."""
        tick = self._tick()
        for predicate, rate in self.schema.volatile.items():
            prior = self.schema.prior(predicate)
            for key in sorted(self._by_predicate.get(predicate, ())):
                b = self.beliefs[key]
                if tick - b.updated_tick > 3:
                    b.confidence += (prior - b.confidence) * rate
                    b.status = self._status(b)
        for k in [k for k, t in self.critical.items() if tick - t > 10]:
            del self.critical[k]

    # ------------------------------------------------------------------ queries
    def confidence(self, s: str, p: str, o: str, default: float | None = None) -> float:
        b = self.beliefs.get((s, p, o))
        if b is None:
            return self.schema.prior(p) if default is None else default
        return b.confidence

    def holds(self, s: str, p: str, o: str, threshold: float = 0.7) -> bool:
        b = self.beliefs.get((s, p, o))
        return b is not None and b.confidence >= threshold

    def query(self, s: str | None = None, p: str | None = None, o: str | None = None,
              min_conf: float = 0.0, max_conf: float = 1.0) -> list[Belief]:
        candidates: set[Fact] | None = None
        for term, index in ((s, self._by_subject), (p, self._by_predicate), (o, self._by_object)):
            if term is None or is_var(term):
                continue
            keys = index.get(term, set())
            candidates = set(keys) if candidates is None else candidates & keys
        if candidates is None:
            candidates = set(self.beliefs)
        # sorted: set iteration order varies between processes, and cognition must be reproducible
        out = [self.beliefs[k] for k in sorted(candidates)]
        return [b for b in out if min_conf <= b.confidence <= max_conf]

    def match(self, pattern: Fact, min_conf: float) -> list[Belief]:
        s, p, o = pattern
        return self.query(None if is_var(s) else s, None if is_var(p) else p,
                          None if is_var(o) else o, min_conf=min_conf)

    def objects(self, s: str, p: str, min_conf: float = 0.5) -> list[str]:
        return [b.object for b in self.query(s, p, None, min_conf=min_conf)]

    def subjects(self, p: str, o: str, min_conf: float = 0.5) -> list[str]:
        return [b.subject for b in self.query(None, p, o, min_conf=min_conf)]

    def entities_of_type(self, type_name: str) -> list[str]:
        return sorted(self.subjects("is_a", type_name, 0.5))

    def open_contradictions(self) -> list[Contradiction]:
        return [self.contradictions[c] for c in self._open_contradiction_by_key.values()]

    def total_uncertainty(self) -> float:
        return sum(b.entropy for b in self.beliefs.values())

    def entity_uncertainty(self, entity: str) -> float:
        keys = self._by_subject.get(entity, ())
        return sum(self.beliefs[k].entropy for k in keys if k[1] in self.schema.epistemic)

    def critical_uncertain(self, low: float = 0.3, high: float = 0.8) -> list[Belief]:
        return [self.beliefs[k] for k in sorted(self.critical) if k in self.beliefs
                and low <= self.beliefs[k].confidence <= high]

    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in EpistemicStatus}
        for b in self.beliefs.values():
            counts[b.status.value] += 1
        return counts

    def sample_evolution(self) -> None:
        self.evolution.append({
            "tick": self._tick(), "beliefs": len(self.beliefs),
            "uncertainty": round(self.total_uncertainty(), 3),
            "open_contradictions": len(self._open_contradiction_by_key),
            **self.status_counts(),
        })

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "beliefs": [b.to_dict() | {"prior": b.prior,
                                       "ev": [(e.source, e.tick, e.positive, e.reliability) for e in b.evidence]}
                        for b in self.beliefs.values()],
            "contradictions": [c.to_dict() for c in self.contradictions.values()],
            "sources": {k: {"alpha": v.alpha, "beta": v.beta, "nominal": v.nominal,
                            "verified": v.verified, "refuted": v.refuted} for k, v in self.sources.items()},
            "coverage": [[k[0], k[1], v[0], v[1]] for k, v in self.coverage.items()],
            "quantities": self.quantities,
            "hypotheses": [h.to_dict() for h in self.hypotheses.items.values()],
            "revision": self.revision,
            "cumulative_uncertainty_reduction": self.cumulative_uncertainty_reduction,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        for item in data["beliefs"]:
            key = (item["s"], item["p"], item["o"])
            b = Belief(item["s"], item["p"], item["o"], item["confidence"], item["prior"],
                       EpistemicStatus(item["status"]), item["created"], item["updated"],
                       evidence=[Evidence(*e) for e in item["ev"]],
                       history=[tuple(h) for h in item["history"]],
                       contradiction_open=item["contradiction"], rationale=item.get("rationale", ""))
            self.beliefs[key] = b
            self._index(key)
        for c in data["contradictions"]:
            rec = Contradiction(c["id"], tuple(c["key"]), c["tick"], c["prior"], c["new"], c["source"],
                                c["severity"], c["resolved_tick"], c["resolution"])
            self.contradictions[rec.id] = rec
            if rec.open:
                self._open_contradiction_by_key[rec.key] = rec.id
        self._cseq = len(self.contradictions)
        for name, s in data["sources"].items():
            src = SourceReliability(s["nominal"])
            src.alpha, src.beta, src.verified, src.refuted = s["alpha"], s["beta"], s["verified"], s["refuted"]
            self.sources[name] = src
        for e, p, count, last in data["coverage"]:
            self.coverage[(e, p)] = (count, last)
        self.quantities.update(data["quantities"])
        self.revision = data["revision"]
        self.cumulative_uncertainty_reduction = data["cumulative_uncertainty_reduction"]
