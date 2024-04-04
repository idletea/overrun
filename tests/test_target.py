from __future__ import annotations

from typing import Any
from overrun.runtime import Context
from overrun.target import Target


class Base:
    def __init__(self, *, context: Context, **kwargs: Any): ...


class IsStartable(Base):
    async def start(self, *, context: Context, **kwargs: Any): ...


class IsRunable(Base):
    async def run(self, *, context: Context, **kwargs: Any): ...


class IsStopable(Base):
    async def stop(self, *, context: Context, **kwargs: Any): ...


class IsResetable(Base):
    async def reset(self, *, context: Context, **kwargs: Any): ...


class IsStartableAndStoppable(IsStartable, IsStopable):
    pass


def test_component_sorting():
    components = [
        IsStartable(context=None),  # type: ignore
        IsRunable(context=None),  # type: ignore
        IsStopable(context=None),  # type: ignore
        IsResetable(context=None),  # type: ignore
        IsStartableAndStoppable(context=None),  # type: ignore
    ]
    target = Target(name="foo", components=components)
    assert target.startable
    assert len(target._startable) == 2
    assert target.runable
    assert len(target._runable) == 1
    assert target.stopable
    assert len(target._stopable) == 2
    assert target.resetable
    assert len(target._resetable) == 1

    components = [
        IsStartable(context=None),  # type: ignore
        IsStartableAndStoppable(context=None),  # type: ignore
    ]
    target = Target(name="bar", components=components)
    assert target.startable
    assert len(target._startable) == 2
    assert not target.runable
    assert len(target._runable) == 0
    assert target.stopable
    assert len(target._stopable) == 1
    assert not target.resetable
    assert len(target._resetable) == 0
