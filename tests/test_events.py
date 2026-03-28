"""Tests for soma.events.EventBus."""

import pytest
from soma.events import EventBus


def test_subscribe_and_emit():
    bus = EventBus()
    received = []
    bus.on("ping", lambda d: received.append(d))
    bus.emit("ping", {"value": 1})
    assert received == [{"value": 1}]


def test_multiple_subscribers():
    bus = EventBus()
    log: list[str] = []
    bus.on("ev", lambda d: log.append("first"))
    bus.on("ev", lambda d: log.append("second"))
    bus.emit("ev", {})
    assert log == ["first", "second"]


def test_unsubscribe():
    bus = EventBus()
    log: list[int] = []

    def handler(d: dict) -> None:
        log.append(d["n"])

    bus.on("tick", handler)
    bus.emit("tick", {"n": 1})
    bus.off("tick", handler)
    bus.emit("tick", {"n": 2})

    assert log == [1]


def test_unsubscribe_unknown_handler_no_error():
    bus = EventBus()
    bus.off("noevent", lambda d: None)  # should not raise


def test_unknown_event_no_error():
    bus = EventBus()
    bus.emit("ghost", {"x": 42})  # no handlers registered — should not raise


def test_emit_passes_data_correctly():
    bus = EventBus()
    captured = {}

    def capture(d: dict) -> None:
        captured.update(d)

    bus.on("data", capture)
    bus.emit("data", {"key": "value", "num": 7})
    assert captured == {"key": "value", "num": 7}


def test_multiple_events_independent():
    bus = EventBus()
    log: list[str] = []
    bus.on("a", lambda d: log.append("a"))
    bus.on("b", lambda d: log.append("b"))
    bus.emit("a", {})
    assert log == ["a"]
    bus.emit("b", {})
    assert log == ["a", "b"]
