# Legacy store protocol. Use soma.persistence for engine state.
"""Store abstractions: Protocol, InMemoryStore, JSONFileStore."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> list[str]: ...


class InMemoryStore:
    """Simple dict-backed in-memory store."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._data.keys())


class JSONFileStore:
    """JSON-file-backed store. Auto-loads on init if the file exists."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = str(path)
        self._data: dict[str, Any] = {}
        if os.path.exists(self._path):
            self._load()

    def _load(self) -> None:
        with open(self._path, "r", encoding="utf-8") as fh:
            self._data = json.load(fh)

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._data.keys())
