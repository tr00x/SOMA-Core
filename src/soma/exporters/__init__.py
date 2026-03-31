"""SOMA Exporter protocol and base classes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Exporter(Protocol):
    """Protocol for SOMA exporters. Implement on_action and on_mode_change."""

    def on_action(self, data: dict) -> None: ...

    def on_mode_change(self, data: dict) -> None: ...

    def shutdown(self) -> None: ...


__all__ = ["Exporter"]
