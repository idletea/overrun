from __future__ import annotations

import asyncio
import sys
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any, Iterator
import pytest
from overrun import component
from overrun.component import Component
from overrun.runtime import Context, Runtime
from overrun.types import ComponentDef, TargetDef


@component.register
class DummyComponent:
    def __init__(self, *, context: Context, **kwargs: Any): ...


@component.register
class BarrierComponent:
    barrier: asyncio.Barrier | None

    def __init__(self, *, context: Context, **kwargs: Any):  # noqa: ARG002
        self.barrier = kwargs["barrier"]

    async def start(self, *, context: Context) -> None:  # noqa: ARG002
        if self.barrier:
            await self.barrier.wait()


@pytest.fixture
def counter() -> Iterator[int]:
    return iter(range(sys.maxsize))


@pytest.fixture
def target_def(counter: Iterator[int]):
    def inner(
        name: str | None = None,
        path: Path | None = None,
        dependencies: set[TargetDef] | None = None,
        component_defs: list[ComponentDef] | None = None,
    ):
        return TargetDef(
            name=name or f"target_{next(counter)}",
            path=path or Path(),
            dependencies=dependencies or set(),
            component_defs=component_defs or [],
        )

    return inner


@pytest.fixture
def component_def():
    def inner(
        name: str | None = None,
        cls: type[Component] | None = None,
        args: dict[str, Any] | None = None,
    ):
        cls = cls or DummyComponent
        return ComponentDef(name=name or cls.__name__, cls=cls, args=args or {})

    return inner


def build_graph(*target_defs: TargetDef) -> TopologicalSorter[TargetDef]:
    graph: TopologicalSorter[TargetDef] = TopologicalSorter()
    for target_def in target_defs:
        graph.add(target_def, *target_def.dependencies)
    graph.prepare()
    return graph


@pytest.mark.asyncio
async def test_targets_can_start_concurrently(
    target_def, component_def, default_runtime: Runtime
):
    """Two targets not mutually dependent should be able to start concurrently."""
    barrier = asyncio.Barrier(parties=2)

    c1 = target_def(
        component_defs=[component_def(cls=BarrierComponent, args={"barrier": barrier})],
    )
    c2 = target_def(
        component_defs=[component_def(cls=BarrierComponent, args={"barrier": barrier})],
    )
    top = target_def(dependencies={c1, c2})

    async with asyncio.timeout(0.1):
        await default_runtime._run(target_graph=build_graph(top, c1, c2))
