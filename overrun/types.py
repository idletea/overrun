from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from overrun.component import Component

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ComponentDef:
    name: str
    cls: type[Component]
    args: dict[str, Any]


class TargetDoc(BaseModel):
    """The deserializer for target files.

    This is the most definitive source of information on
    what keys and values are valid within a target file.
    """

    model_config = ConfigDict(extra="allow")

    class Target(BaseModel):
        name: str | None = None
        dependencies: list[str] | None = None

    path: Path  # path of the file defining this target
    target: Target = Field(default_factory=Target)


@dataclass(slots=True, frozen=True)
class TargetDef:
    """A target's definition; what's needed to instantiate a target."""

    name: str
    path: Path  # path of the file defining this target
    dependencies: set[TargetDef]
    component_defs: list[ComponentDef]

    def __hash__(self) -> int:
        return hash(f"{self.name}{self.path}")
