"""Fixed-size ring buffer for agent action history."""

from __future__ import annotations

from collections import deque
from typing import Generic, Iterator, TypeVar, overload

T = TypeVar("T")


class RingBuffer(Generic[T]):
    """Fixed-capacity ring buffer. Oldest items dropped on overflow."""

    __slots__ = ("_buf", "capacity")

    def __init__(self, capacity: int = 10) -> None:
        self._buf: deque[T] = deque(maxlen=capacity)
        self.capacity = capacity

    def append(self, item: T) -> None:
        self._buf.append(item)

    def last(self, n: int) -> list[T]:
        items = list(self._buf)
        return items[-n:] if n < len(items) else items

    def clear(self) -> None:
        self._buf.clear()

    @overload
    def __getitem__(self, index: int) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self._buf)[index]
        return self._buf[index]

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Iterator[T]:
        return iter(self._buf)

    def __bool__(self) -> bool:
        return len(self._buf) > 0

    def __repr__(self) -> str:
        return f"RingBuffer(capacity={self.capacity}, items={list(self._buf)})"
