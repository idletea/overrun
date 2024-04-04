from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self
from overrun.component import Component, Resetable, Runable, Startable, Stopable

if TYPE_CHECKING:
    from overrun.runtime import Context
    from overrun.types import TargetDef

logger = logging.getLogger(__name__)


@dataclass
class Target:
    """An instance of a target, containing instantiated components."""

    name: str
    components: list[Component]

    _startable: list[Startable] = field(default_factory=list)
    _runable: list[Runable] = field(default_factory=list)
    _stopable: list[Stopable] = field(default_factory=list)
    _resetable: list[Resetable] = field(default_factory=list)

    @classmethod
    def from_target_def(
        cls: type[Self], *, target_def: TargetDef, context: Context
    ) -> Self:
        return cls(
            name=target_def.name,
            components=[
                component_def.cls(
                    context=context,
                    **component_def.args,
                )
                for component_def in target_def.component_defs
            ],
        )

    def __post_init__(self):
        for component in self.components:
            if isinstance(component, Startable):
                self._startable.append(component)
            if isinstance(component, Runable):
                self._runable.append(component)
            if isinstance(component, Stopable):
                self._stopable.append(component)
            if isinstance(component, Resetable):
                self._resetable.append(component)

    @property
    def startable(self) -> bool:
        return bool(self._startable)

    @property
    def runable(self) -> bool:
        return bool(self._runable)

    @property
    def stopable(self) -> bool:
        return bool(self._stopable)

    @property
    def resetable(self) -> bool:
        return bool(self._resetable)

    def __hash__(self) -> int:
        """Bit hacky, but overrun should exit before allowing conflicting Targets."""
        return hash(self.name)

    async def start(self, *, context: Context) -> None:
        for component in self._startable:
            await component.start(context=context)

    async def run(self, *, context: Context) -> None:
        async with asyncio.TaskGroup() as tg:
            for component in self._runable:
                tg.create_task(component.run(context=context))

    async def stop(self, *, context: Context) -> None:
        for component in reversed(self._stopable):
            await component.stop(context=context)

    async def reset(self, *, context: Context) -> None:
        async with asyncio.TaskGroup() as tg:
            for component in self._resetable:
                tg.create_task(component.reset(context=context))
