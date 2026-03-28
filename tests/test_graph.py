"""Tests for soma.graph.PressureGraph."""

import pytest
from soma.graph import PressureGraph


def make_graph(**kwargs) -> PressureGraph:
    defaults = dict(damping=0.6, decay_rate=0.05, recovery_rate=0.02)
    defaults.update(kwargs)
    return PressureGraph(**defaults)


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

def test_add_agents():
    g = make_graph()
    g.add_agent("a")
    g.add_agent("b")
    assert g.agents == {"a", "b"}


def test_add_edge_creates_agents():
    g = make_graph()
    g.add_edge("x", "y", trust=0.8)
    assert {"x", "y"} <= g.agents
    assert g.get_trust("x", "y") == pytest.approx(0.8)


def test_set_and_get_internal_pressure():
    g = make_graph()
    g.add_agent("a")
    g.set_internal_pressure("a", 0.5)
    # effective not set yet — default is 0
    assert g.get_effective_pressure("a") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------

def test_propagation_increases_effective():
    g = make_graph(damping=0.6)
    g.add_edge("src", "tgt", trust=1.0)
    g.set_internal_pressure("src", 1.0)
    g.set_internal_pressure("tgt", 0.0)
    g.propagate()
    assert g.get_effective_pressure("tgt") > 0.0


def test_damping_limits_incoming():
    """With damping=0.6, source=1.0, target=0.0 → effective ≈ 0.6."""
    g = make_graph(damping=0.6)
    g.add_edge("src", "tgt", trust=1.0)
    g.set_internal_pressure("src", 1.0)
    g.set_internal_pressure("tgt", 0.0)
    g.propagate()
    assert g.get_effective_pressure("tgt") == pytest.approx(0.6)


def test_no_edge_no_propagation():
    """Without edges effective pressure equals internal pressure."""
    g = make_graph()
    g.add_agent("solo")
    g.set_internal_pressure("solo", 0.9)
    g.propagate()
    assert g.get_effective_pressure("solo") == pytest.approx(0.9)


def test_internal_pressure_wins_over_incoming():
    """If internal > damping * incoming, effective = internal."""
    g = make_graph(damping=0.6)
    g.add_edge("src", "tgt", trust=1.0)
    g.set_internal_pressure("src", 0.5)   # damping * 0.5 = 0.3
    g.set_internal_pressure("tgt", 0.8)   # internal wins
    g.propagate()
    assert g.get_effective_pressure("tgt") == pytest.approx(0.8)


def test_multi_source_averaged():
    """Two sources with equal trust → weighted average of their pressures."""
    g = make_graph(damping=1.0)  # damping=1 so effective == weighted_avg
    g.add_edge("a", "tgt", trust=1.0)
    g.add_edge("b", "tgt", trust=1.0)
    g.set_internal_pressure("a", 0.8)
    g.set_internal_pressure("b", 0.4)
    g.set_internal_pressure("tgt", 0.0)
    g.propagate()
    assert g.get_effective_pressure("tgt") == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Trust mutation
# ---------------------------------------------------------------------------

def test_trust_decay():
    g = make_graph(decay_rate=0.1)
    g.add_edge("src", "tgt", trust=0.8)
    g.decay_trust("src", uncertainty=1.0)
    assert g.get_trust("src", "tgt") == pytest.approx(0.7)


def test_trust_recovery():
    g = make_graph(recovery_rate=0.1)
    g.add_edge("src", "tgt", trust=0.5)
    g.recover_trust("src", uncertainty=0.0)
    assert g.get_trust("src", "tgt") == pytest.approx(0.6)


def test_trust_clamp_lower():
    g = make_graph(decay_rate=0.5)
    g.add_edge("src", "tgt", trust=0.1)
    g.decay_trust("src", uncertainty=1.0)
    g.decay_trust("src", uncertainty=1.0)
    assert g.get_trust("src", "tgt") == pytest.approx(0.0)


def test_trust_clamp_upper():
    g = make_graph(recovery_rate=0.5)
    g.add_edge("src", "tgt", trust=0.9)
    g.recover_trust("src", uncertainty=0.0)
    g.recover_trust("src", uncertainty=0.0)
    assert g.get_trust("src", "tgt") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def test_to_dict_keys():
    g = make_graph()
    g.add_agent("a")
    g.add_edge("a", "b", trust=0.7)
    d = g.to_dict()
    assert "damping" in d
    assert "decay_rate" in d
    assert "recovery_rate" in d
    assert "nodes" in d
    assert "edges" in d


def test_to_dict_edge_data():
    g = make_graph()
    g.add_edge("x", "y", trust=0.5)
    d = g.to_dict()
    edge = next(e for e in d["edges"] if e["source"] == "x" and e["target"] == "y")
    assert edge["trust_weight"] == pytest.approx(0.5)


def test_to_dict_node_pressures():
    g = make_graph(damping=0.6)
    g.add_edge("s", "t", trust=1.0)
    g.set_internal_pressure("s", 1.0)
    g.propagate()
    d = g.to_dict()
    node_t = next(n for n in d["nodes"] if n["agent_id"] == "t")
    assert node_t["effective_pressure"] == pytest.approx(0.6)
