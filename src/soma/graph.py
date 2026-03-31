"""PressureGraph — trust-weighted pressure propagation across agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from soma.types import PressureVector


@dataclass
class _Node:
    agent_id: str
    internal_pressure: float = 0.0
    effective_pressure: float = 0.0
    internal_pressure_vector: PressureVector | None = None
    effective_pressure_vector: PressureVector | None = None


@dataclass
class _Edge:
    source: str
    target: str
    trust_weight: float = 1.0


class PressureGraph:
    """Directed graph that propagates internal pressure along trust-weighted edges."""

    def __init__(
        self,
        damping: float = 0.6,
        decay_rate: float = 0.05,
        recovery_rate: float = 0.02,
        snr_threshold: float = 0.5,
    ) -> None:
        self.damping = damping
        self.decay_rate = decay_rate
        self.recovery_rate = recovery_rate
        self.snr_threshold = snr_threshold
        self._nodes: dict[str, _Node] = {}
        # edges[target] = list of _Edge leading into that target
        self._edges: dict[str, list[_Edge]] = {}
        # outgoing edges keyed by source for trust mutation helpers
        self._out_edges: dict[str, list[_Edge]] = {}
        # Coordination SNR per agent (updated during propagate)
        self._snr: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_agent(self, agent_id: str) -> None:
        if agent_id not in self._nodes:
            self._nodes[agent_id] = _Node(agent_id=agent_id)
            self._edges[agent_id] = []
            self._out_edges[agent_id] = []

    def add_edge(self, source: str, target: str, trust: float = 1.0) -> None:
        for node_id in (source, target):
            if node_id not in self._nodes:
                self.add_agent(node_id)
        edge = _Edge(source=source, target=target, trust_weight=float(trust))
        self._edges[target].append(edge)
        self._out_edges[source].append(edge)

    # ------------------------------------------------------------------
    # Pressure accessors
    # ------------------------------------------------------------------

    def set_internal_pressure(self, agent_id: str, pressure: float) -> None:
        self._nodes[agent_id].internal_pressure = float(pressure)

    def get_effective_pressure(self, agent_id: str) -> float:
        return self._nodes[agent_id].effective_pressure

    def set_internal_pressure_vector(self, agent_id: str, vector: PressureVector) -> None:
        self._nodes[agent_id].internal_pressure_vector = vector

    def get_effective_pressure_vector(self, agent_id: str) -> PressureVector | None:
        return self._nodes[agent_id].effective_pressure_vector

    def get_snr(self, agent_id: str) -> float:
        """Coordination SNR for agent: 1.0 if no incoming edges or not yet computed."""
        return self._snr.get(agent_id, 1.0)

    # ------------------------------------------------------------------
    # Graph properties
    # ------------------------------------------------------------------

    @property
    def agents(self) -> set[str]:
        return set(self._nodes.keys())

    def get_trust(self, source: str, target: str) -> float:
        for edge in self._edges.get(target, []):
            if edge.source == source:
                return edge.trust_weight
        raise KeyError(f"No edge from {source!r} to {target!r}")

    # ------------------------------------------------------------------
    # Propagation
    # ------------------------------------------------------------------

    def propagate(self, max_iterations: int = 3) -> None:
        """Multi-pass propagation until stable or max iterations.

        Propagates both scalar effective_pressure and per-signal
        effective_pressure_vector independently. Scalar is used for
        ResponseMode mapping; vector enables downstream agents to react
        precisely to the cause of upstream pressure.

        Coordination SNR (PRS-02): before propagating into a node, compute the
        ratio of error-backed incoming pressure to total incoming pressure. If
        SNR < snr_threshold and incoming pressure is non-trivial (> 0.05), the
        node is isolated — it uses only its own internal pressure rather than
        absorbing potentially-noisy upstream signals.
        """
        for _ in range(max_iterations):
            changed = False
            for node_id, node in self._nodes.items():
                old_effective = node.effective_pressure
                incoming_edges = self._edges[node_id]

                if not incoming_edges:
                    # No incoming edges — use internal pressure, SNR=1.0
                    node.effective_pressure = node.internal_pressure
                    if node.internal_pressure_vector is not None:
                        node.effective_pressure_vector = node.internal_pressure_vector
                    self._snr[node_id] = 1.0
                else:
                    total_weight = sum(e.trust_weight for e in incoming_edges)

                    # --- Coordination SNR (PRS-02) ---
                    isolated = False
                    # Only compute SNR when upstream sources have pressure vectors;
                    # without vectors we cannot distinguish signal from noise.
                    sources_with_vector = [
                        e for e in incoming_edges
                        if self._nodes[e.source].effective_pressure_vector is not None
                    ]
                    if total_weight > 0.0 and sources_with_vector:
                        total_incoming = sum(
                            e.trust_weight * self._nodes[e.source].effective_pressure
                            for e in incoming_edges
                        ) / total_weight
                        confirmed_incoming = sum(
                            e.trust_weight * self._nodes[e.source].effective_pressure_vector.error_rate
                            for e in sources_with_vector
                        ) / total_weight
                        snr = confirmed_incoming / max(total_incoming, 0.001)
                        self._snr[node_id] = snr
                        # Only isolate when there is meaningful incoming pressure
                        if total_incoming > 0.05 and snr < self.snr_threshold:
                            isolated = True
                    else:
                        self._snr[node_id] = 1.0

                    if isolated:
                        # Isolation: use internal pressure only; skip upstream influence
                        node.effective_pressure = node.internal_pressure
                        if node.internal_pressure_vector is not None:
                            node.effective_pressure_vector = node.internal_pressure_vector
                    else:
                        # --- scalar propagation ---
                        if total_weight == 0.0:
                            weighted_avg = 0.0
                        else:
                            weighted_avg = sum(
                                e.trust_weight * self._nodes[e.source].effective_pressure
                                for e in incoming_edges
                            ) / total_weight
                        node.effective_pressure = max(
                            node.internal_pressure, self.damping * weighted_avg
                        )

                        # --- vector propagation ---
                        if node.internal_pressure_vector is not None:
                            upstream = [
                                (e.trust_weight, self._nodes[e.source].effective_pressure_vector)
                                for e in incoming_edges
                                if self._nodes[e.source].effective_pressure_vector is not None
                            ]
                            if not upstream or total_weight == 0.0:
                                node.effective_pressure_vector = node.internal_pressure_vector
                            else:
                                def _blend(own: float, vals: list[tuple[float, float]]) -> float:
                                    weighted_sum = sum(w * v for w, v in vals)
                                    return max(own, self.damping * weighted_sum / total_weight)

                                iv = node.internal_pressure_vector
                                node.effective_pressure_vector = PressureVector(
                                    uncertainty=_blend(iv.uncertainty, [(w, v.uncertainty) for w, v in upstream]),
                                    drift=_blend(iv.drift, [(w, v.drift) for w, v in upstream]),
                                    error_rate=_blend(iv.error_rate, [(w, v.error_rate) for w, v in upstream]),
                                    cost=_blend(iv.cost, [(w, v.cost) for w, v in upstream]),
                                )

                if abs(node.effective_pressure - old_effective) > 1e-6:
                    changed = True
            if not changed:
                break

    # ------------------------------------------------------------------
    # Trust mutation
    # ------------------------------------------------------------------

    def _get_outgoing_edges(self, source: str) -> list[_Edge]:
        return self._out_edges.get(source, [])

    def decay_trust(self, source: str, uncertainty: float) -> None:
        for edge in self._get_outgoing_edges(source):
            edge.trust_weight = max(
                0.0, min(1.0, edge.trust_weight - self.decay_rate * uncertainty)
            )

    def recover_trust(self, source: str, uncertainty: float) -> None:
        for edge in self._get_outgoing_edges(source):
            edge.trust_weight = max(
                0.0,
                min(1.0, edge.trust_weight + self.recovery_rate * (1.0 - uncertainty)),
            )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        edges: list[dict[str, Any]] = []
        for target_edges in self._edges.values():
            for e in target_edges:
                edges.append(
                    {"source": e.source, "target": e.target, "trust_weight": e.trust_weight}
                )
        return {
            "damping": self.damping,
            "decay_rate": self.decay_rate,
            "recovery_rate": self.recovery_rate,
            "snr_threshold": self.snr_threshold,
            "nodes": [
                {
                    "agent_id": n.agent_id,
                    "internal_pressure": n.internal_pressure,
                    "effective_pressure": n.effective_pressure,
                    "internal_pressure_vector": n.internal_pressure_vector.to_dict() if n.internal_pressure_vector else None,
                    "effective_pressure_vector": n.effective_pressure_vector.to_dict() if n.effective_pressure_vector else None,
                }
                for n in self._nodes.values()
            ],
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PressureGraph":
        obj = cls(
            damping=data.get("damping", 0.6),
            decay_rate=data.get("decay_rate", 0.05),
            recovery_rate=data.get("recovery_rate", 0.02),
            snr_threshold=data.get("snr_threshold", 0.5),
        )
        for node_data in data.get("nodes", []):
            agent_id = node_data["agent_id"]
            obj.add_agent(agent_id)
            obj._nodes[agent_id].internal_pressure = node_data.get("internal_pressure", 0.0)
            obj._nodes[agent_id].effective_pressure = node_data.get("effective_pressure", 0.0)
            if node_data.get("internal_pressure_vector"):
                obj._nodes[agent_id].internal_pressure_vector = PressureVector.from_dict(
                    node_data["internal_pressure_vector"]
                )
            if node_data.get("effective_pressure_vector"):
                obj._nodes[agent_id].effective_pressure_vector = PressureVector.from_dict(
                    node_data["effective_pressure_vector"]
                )
        for edge_data in data.get("edges", []):
            obj.add_edge(edge_data["source"], edge_data["target"], edge_data.get("trust_weight", 1.0))
        return obj
