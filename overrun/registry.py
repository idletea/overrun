from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any, Generator, Self
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from overrun.component import Component
from overrun.config import Config, ConfigFailed

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Registry:
    target_directories: dict[Path, set[Path]]
    component_types: dict[str, type[Component]]

    @classmethod
    def attempt_init(
        cls: type[Self], config: Config | ConfigFailed
    ) -> Self | RegistryFailed:
        if isinstance(config, ConfigFailed):
            return RegistryFailed(cause=RegistryFailed.Cause.NoConfig)

        valid_docs, invalid_docs = _deserialize_target_documents(
            config.target_directories
        )

        # we promote valid documents to definitions before checking
        # for invalid docs to detect and report name collisions
        definitions = _build_target_definitions(valid_docs)

        raise NotImplementedError()


@dataclass(slots=True, frozen=True)
class RegistryFailed:
    """Context about why a valid `Registry` could not be constructed."""

    class Cause(StrEnum):
        NoConfig = "There is no valid configuration; cannot infer directories to scan"
        DependencyCycle = "A dependency cycle exists in the targets"

    cause: Cause
    additional_context: str | None = None


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
        dependencies: list[str] = Field(default_factory=list)

    path: Path  # path of the file defining this target
    project: Path  # project path in which this target exists
    target: Target = Field(default_factory=Target)


@dataclass(slots=True, frozen=True)
class TargetDefinition:
    """A target's definition; what's needed to instantiate a target."""

    name: str
    path: Path  # path of the file defining this target
    project: Path  # project path in which this target exists
    dependencies: set[TargetDefinition]
    components: list[ComponentDefinition]

    def __hash__(self) -> int:
        return hash(f"{self.name}{self.path}")


@dataclass(slots=True, frozen=True)
class TargetErrors(Exception):
    """One or more targets are invalid."""

    valid_targets: list[TargetDocument]
    invalid_targets: list[tuple[Path, str]]


def _deserialize_target_documents(
    target_directories: dict[Path, set[Path]],
) -> tuple[list[TargetDocument], list[tuple[Path, str]]]:
    valid_targets: list[TargetDocument] = []
    invalid_targets: list[tuple[Path, str]] = []

    for _project_dir, project_target_dirs in target_directories.items():
        for target_dir in project_target_dirs:
            if not target_dir.exists():
                logger.warn(f"Target directory {target_dir} does not exist")
            elif not target_dir.is_dir():
                logger.warn(f"Target directory {target_dir} is not a directory")
            else:
                logger.debug(f"Searching {target_dir} for targets")

                for result in _search_target_dir(target_dir):
                    if isinstance(result, TargetDocument):
                        valid_targets.append(result)
                    else:
                        invalid_targets.append(result)

    return valid_targets, invalid_targets


def _search_target_dir(
    dir: Path,
) -> Generator[TargetDocument | tuple[Path, str], None, None]:
    for toml in (
        child
        for child in dir.iterdir()
        if child.is_file() and child.name.endswith(".toml")
    ):
        try:
            with toml.open("rb") as fp:
                yield TargetDocument(path=toml, project=dir, **tomllib.load(fp))
        except ValidationError as exc:
            yield toml, ", ".join(error["msg"] for error in exc.errors())


def _build_target_definitions(
    documents: list[TargetDocument],
) -> list[TargetDefinition] | RegistryFailed:
    documents_named = {
        document.target.name or _name_from_path(document.path): document
        for document in documents
    }

    # As a `TargetDefinition` contains its dependencies also as `TargetDefinition`s, we
    # need a dependency graph to construct each definition only after having constructed
    # the dependencies needed for it.
    #
    # Also catches dependency cycles that makes correctly running targets impossible.
    graph: TopologicalSorter[str] = TopologicalSorter()
    for name, document in documents_named.items():
        graph.add(name, *document.target.dependencies)
    try:
        graph.prepare()
    except CycleError as exc:
        cycle_nodes = " -> ".join((node for node in exc.args[1]))
        return RegistryFailed(
            cause=RegistryFailed.Cause.DependencyCycle, additional_context=cycle_nodes
        )

    definitions: dict[str, TargetDefinition] = {}
    while graph.is_active():
        for name in graph.get_ready():
            graph.done(name)

            document = documents_named[name]
            definitions[name] = TargetDefinition(
                name=name,
                path=document.path,
                project=document.project,
                dependencies={definitions[dep] for dep in document.target.dependencies},
                components=[],  # todo
            )

    return list(definitions.values())


def _name_from_path(path: Path) -> str:
    return path.name[0 : -(len(path.suffix))]
