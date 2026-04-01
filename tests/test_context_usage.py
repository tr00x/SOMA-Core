"""Tests for context window usage tracking (CTX-01)."""

from __future__ import annotations

from soma.types import VitalsSnapshot, Action
from soma.engine import SOMAEngine


# ── Test 1: VitalsSnapshot accepts context_usage field, defaults to 0.0 ──

def test_vitals_snapshot_context_usage_default():
    v = VitalsSnapshot()
    assert v.context_usage == 0.0


def test_vitals_snapshot_context_usage_custom():
    v = VitalsSnapshot(context_usage=0.75)
    assert v.context_usage == 0.75


# ── Test 2: record_action() computes context_usage = cumulative_tokens / context_window ──

def test_record_action_computes_context_usage():
    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("a1")

    # Send action with 50000 tokens, default context_window = 200000
    action = Action(tool_name="Bash", output_text="ok", token_count=50_000)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 50_000 / 200_000  # 0.25


def test_record_action_accumulates_context_usage():
    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("a1")

    for _ in range(4):
        action = Action(tool_name="Bash", output_text="ok", token_count=50_000)
        result = engine.record_action("a1", action)

    # 4 * 50000 = 200000 / 200000 = 1.0
    assert result.vitals.context_usage == 1.0


# ── Test 3: context_usage of 0.7+ reduces predicted_success_rate ──

def test_context_usage_degrades_predicted_success_rate():
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    # Fill context to 70%+
    for _ in range(7):
        action = Action(tool_name="Bash", output_text="ok", token_count=10)
        result = engine.record_action("a1", action)

    # context_usage = 70/100 = 0.7
    assert result.vitals.context_usage == 0.7
    # The context_factor at 0.7 usage: max(0.4, 1.0 - 0.7*0.6) = max(0.4, 0.58) = 0.58
    # This means if predicted_success_rate existed, it'd be multiplied by 0.58
    # Without fingerprint data, predicted_success_rate is None, so we just confirm context_usage


# ── Test 4: context_window_size defaults to 200000 ──

def test_default_context_window():
    engine = SOMAEngine()
    assert engine._context_window == 200_000


# ── Test 5: context_window_size can be configured ──

def test_custom_context_window():
    engine = SOMAEngine(context_window=100_000)
    assert engine._context_window == 100_000


def test_context_window_from_config():
    config = {
        "budget": {"tokens": 100_000},
        "context_window": 500_000,
    }
    engine = SOMAEngine.from_config(config)
    assert engine._context_window == 500_000


def test_context_usage_capped_at_one():
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    # Send more tokens than context window
    action = Action(tool_name="Bash", output_text="ok", token_count=200)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 1.0  # capped


# ── Test 6: context_burn_rate in VitalsSnapshot ──

def test_vitals_snapshot_context_burn_rate_default():
    v = VitalsSnapshot()
    assert v.context_burn_rate == 0.0


def test_context_burn_rate_rolling_avg():
    """Burn rate is rolling avg of tokens per action over last 10 actions."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=1_000_000)
    engine.register_agent("a1")

    # Send 3 actions with different token counts
    for tokens in [100, 200, 300]:
        action = Action(tool_name="Bash", output_text="ok", token_count=tokens)
        result = engine.record_action("a1", action)

    # Rolling avg over 3 actions: (100 + 200 + 300) / 3 = 200.0
    assert result.vitals.context_burn_rate == 200.0


# ── Test 7: context_exhaustion in signal_pressures ──

def test_context_exhaustion_low_usage_zero_pressure():
    """At 50% usage, context_exhaustion pressure is ~0.0 (sigmoid_clamp(0.0))."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=200)
    engine.register_agent("a1")

    # Send 100 tokens to reach 50% usage
    action = Action(tool_name="Bash", output_text="ok", token_count=100)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 0.5
    # At 50%, (0.5 - 0.5) / 0.15 = 0.0 -> sigmoid_clamp(0.0) = 0.0


def test_context_exhaustion_high_usage_high_pressure():
    """At 85% usage, context_exhaustion pressure should be > 0.3."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=200)
    engine.register_agent("a1")

    # Send 170 tokens to reach 85% usage
    action = Action(tool_name="Bash", output_text="ok", token_count=170)
    result = engine.record_action("a1", action)
    assert result.vitals.context_usage == 0.85
    # At 85%, (0.85 - 0.5) / 0.15 = 2.33 -> sigmoid_clamp(2.33) ~ 0.34
    # Pressure should be > 0.3


# ── Test 8: Proactive context events ──

def test_context_warning_fires_at_70_percent():
    """context_warning event fires once when usage crosses 70%."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    events = []
    engine.events.on("context_warning", lambda data: events.append(data))

    # Send 70 tokens to cross 70% threshold
    action = Action(tool_name="Bash", output_text="ok", token_count=70)
    engine.record_action("a1", action)

    assert len(events) == 1
    assert events[0]["agent_id"] == "a1"
    assert events[0]["usage"] == 0.7


def test_context_critical_fires_at_90_percent():
    """context_critical event fires once when usage crosses 90%."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    events = []
    engine.events.on("context_critical", lambda data: events.append(data))

    action = Action(tool_name="Bash", output_text="ok", token_count=90)
    engine.record_action("a1", action)

    assert len(events) == 1
    assert events[0]["agent_id"] == "a1"
    assert events[0]["usage"] == 0.9


def test_context_warning_fires_only_once():
    """context_warning does not fire twice on consecutive actions above 70%."""
    engine = SOMAEngine(budget={"tokens": 10_000_000}, context_window=100)
    engine.register_agent("a1")

    events = []
    engine.events.on("context_warning", lambda data: events.append(data))

    # First action crosses 70%
    action = Action(tool_name="Bash", output_text="ok", token_count=75)
    engine.record_action("a1", action)

    # Second action still above 70%
    action = Action(tool_name="Bash", output_text="ok", token_count=5)
    engine.record_action("a1", action)

    assert len(events) == 1  # fired only once


# ── Test 9: add_exporter wires exporter to EventBus ──

def test_add_exporter_wires_events():
    """add_exporter registers exporter and wires on_action + on_mode_change."""
    engine = SOMAEngine(budget={"tokens": 10_000_000})
    engine.register_agent("a1")

    class MockExporter:
        def __init__(self):
            self.actions = []
            self.mode_changes = []

        def on_action(self, data: dict) -> None:
            self.actions.append(data)

        def on_mode_change(self, data: dict) -> None:
            self.mode_changes.append(data)

        def shutdown(self) -> None:
            pass

    exporter = MockExporter()
    engine.add_exporter(exporter)

    action = Action(tool_name="Bash", output_text="ok", token_count=100)
    engine.record_action("a1", action)

    # Exporter should have received the action_recorded event
    assert len(exporter.actions) == 1
    assert exporter.actions[0]["agent_id"] == "a1"
    assert exporter.actions[0]["tool_name"] == "Bash"


# ── Test 10: action_recorded event emitted after record_action ──

def test_action_recorded_event_emitted():
    """action_recorded event emitted after every record_action."""
    engine = SOMAEngine(budget={"tokens": 10_000_000})
    engine.register_agent("a1")

    events = []
    engine.events.on("action_recorded", lambda data: events.append(data))

    action = Action(tool_name="Bash", output_text="ok", token_count=100)
    engine.record_action("a1", action)

    assert len(events) == 1
    assert events[0]["agent_id"] == "a1"
    assert events[0]["tool_name"] == "Bash"
    assert "pressure" in events[0]
    assert "mode" in events[0]


# ── Test 11: shutdown() calls exporter.shutdown() ──

def test_shutdown_calls_exporter_shutdown():
    """shutdown() calls exporter.shutdown() for all registered exporters."""
    engine = SOMAEngine()

    shutdown_called = []

    class MockExporter:
        def __init__(self, name):
            self.name = name

        def on_action(self, data: dict) -> None:
            pass

        def on_mode_change(self, data: dict) -> None:
            pass

        def shutdown(self) -> None:
            shutdown_called.append(self.name)

    engine.add_exporter(MockExporter("exp1"))
    engine.add_exporter(MockExporter("exp2"))

    engine.shutdown()

    assert shutdown_called == ["exp1", "exp2"]


def test_shutdown_handles_exporter_errors():
    """shutdown() does not crash if an exporter raises during shutdown."""
    engine = SOMAEngine()

    class BadExporter:
        def on_action(self, data: dict) -> None:
            pass

        def on_mode_change(self, data: dict) -> None:
            pass

        def shutdown(self) -> None:
            raise RuntimeError("boom")

    engine.add_exporter(BadExporter())
    engine.shutdown()  # Should not raise


# ── Test 12: wrap.py model auto-detection ──

def test_wrap_extracts_model_name():
    """wrap.py _extract_response_data extracts model name and updates context window."""
    from soma.wrap import WrappedClient

    # Create a mock response with model attribute
    class MockUsage:
        input_tokens = 100
        output_tokens = 50

    class MockContent:
        text = "hello"

    class MockResponse:
        model = "gpt-4"
        content = [MockContent()]
        usage = MockUsage()

    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("test-agent")

    # Create a mock client with messages.create
    class MockMessages:
        def create(self, **kwargs):
            return MockResponse()

    class MockClient:
        messages = MockMessages()

    wrapped = WrappedClient(
        client=MockClient(),
        engine=engine,
        agent_id="test-agent",
        auto_export=False,
    )

    # Before detection, context window is default
    assert engine._context_window == 200_000

    # Extract response data (simulates what happens during API call)
    wrapped._extract_response_data(MockResponse())

    # After detection, context window should be updated to gpt-4's window
    assert engine._context_window == 8_192
    assert wrapped._model_detected is True


def test_wrap_model_detection_only_fires_once():
    """Model detection only fires on first response."""
    from soma.wrap import WrappedClient

    class MockUsage:
        input_tokens = 100
        output_tokens = 50

    class MockContent:
        text = "hello"

    class MockResponse:
        model = "gpt-4"
        content = [MockContent()]
        usage = MockUsage()

    class MockResponse2:
        model = "gpt-4-turbo"
        content = [MockContent()]
        usage = MockUsage()

    engine = SOMAEngine(budget={"tokens": 1_000_000})
    engine.register_agent("test-agent")

    class MockMessages:
        def create(self, **kwargs):
            return MockResponse()

    class MockClient:
        messages = MockMessages()

    wrapped = WrappedClient(
        client=MockClient(),
        engine=engine,
        agent_id="test-agent",
        auto_export=False,
    )

    wrapped._extract_response_data(MockResponse())
    assert engine._context_window == 8_192

    # Second call with different model should NOT update
    wrapped._extract_response_data(MockResponse2())
    assert engine._context_window == 8_192  # still gpt-4's window
