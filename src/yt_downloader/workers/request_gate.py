"""Generation tokens that prevent stale asynchronous results reaching current UI state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RequestToken:
    generation: int
    source: str


class LatestRequestGate(Generic[T]):
    def __init__(self) -> None:
        self._generation = 0
        self.current: RequestToken | None = None

    def begin(self, source: str) -> RequestToken:
        self._generation += 1
        token = RequestToken(self._generation, source)
        self.current = token
        return token

    def is_current(self, token: RequestToken) -> bool:
        return token == self.current

    def deliver(self, token: RequestToken, consumer: Callable[[T], None], value: T) -> bool:
        if not self.is_current(token):
            return False
        consumer(value)
        return True

    def finish(self, token: RequestToken) -> bool:
        if not self.is_current(token):
            return False
        self.current = None
        return True
