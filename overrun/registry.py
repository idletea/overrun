from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from pydantic import BaseModel, ConfigDict, Field
from overrun.component import Component

logger = logging.getLogger(__name__)


@dataclass
class Registry:
    target_directories: dict[Path, set[Path]]
    component_types: dict[str, type[Component]]

    @classmethod
    def attempt_init(cls: type[Self]) -> Self | RegistryFailed:
        pass


@dataclass
class RegistryFailed:
    pass


@dataclass(slots=True, frozen=True)
class ComponentDefinition:
    """A component's definition; what's needed to instantiate a target's component."""

    name: str
    cls: type[Component]
    args: dict[str, Any]


class TargetDocument(BaseModel):
    """The deserializer for target files.

    This is the most definitive source of information on
    what keys and values are valid within a target file.
    """

    model_config = ConfigDict(extra="allow")

    class Target(BaseModel):
        name: str | None = None
        dependencies: list[str] | None = None

    path: Path  # path of the file defining this target
    project: Path  # project path in which this target exists
    target: Target = Field(default_factory=Target)


@dataclass(slots=True, frozen=True)
class TargetDefinition:
    """A target's definition; what's needed to instantiate a target."""

    name: str
    path: Path  # path of the file defining this target
    project_dir: Path  # project path in which this target exists
    dependencies: set[TargetDefinition]
    component_defs: list[ComponentDefinition]

    def __hash__(self) -> int:
        return hash(f"{self.name}{self.path}")
