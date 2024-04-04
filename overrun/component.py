from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from overrun.runtime import Context

logger = logging.getLogger(__name__)
COMPONENT_TYPES: dict[str, type[Component]] = {}


def register(cls: type[Component]) -> type:
    """Register a type as an overrun component."""
    global COMPONENT_TYPES
    name = _camel_case(cls.__name__)
    COMPONENT_TYPES[name] = cls
    return cls


@runtime_checkable
class Startable(Protocol):
    async def start(self, *, context: Context) -> None: ...


@runtime_checkable
class Runable(Protocol):
    async def run(self, *, context: Context) -> None: ...


@runtime_checkable
class Stopable(Protocol):
    async def stop(self, *, context: Context) -> None: ...


@runtime_checkable
class Resetable(Protocol):
    async def reset(self, *, context: Context) -> None: ...


class Component(Protocol):
    """A component which implements any subset of the lifecycle methods."""

    def __init__(self, *, context: Context, **kwargs: Any): ...


def _camel_case(s: str) -> str:
    return re.sub(
        "([a-z0-9])([A-Z])",
        r"\1_\2",
        re.sub("(.)([A-Z][a-z]+)", r"\1_\2", s),
    ).lower()
