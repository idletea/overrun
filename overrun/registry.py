from __future__ import annotations

import logging
import tomllib
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Iterable
from pydantic import ValidationError

# importing for side effect of component registration
import overrun.components  # noqa: F401
from overrun.component import COMPONENT_TYPES, Component
from overrun.exceptions import TargetErrors
from overrun.types import ComponentDef, TargetDef, TargetDoc

logger = logging.getLogger(__name__)


class Registry:
    """Registry of defined targets and their components."""

    target_docs: dict[str, TargetDoc]
    component_types: dict[str, type[Component]]

    def __init__(
        self,
        *,
        target_dirs: Iterable[Path],
        component_types: dict[str, type[Component]] | None = None,
    ):
        deserialized_docs = _deserialize_target_docs(target_dirs)
        self.target_docs = _determine_names(deserialized_docs)
        self.component_types = component_types if component_types else COMPONENT_TYPES

    def depedency_graph(self, *, target_name: str) -> TopologicalSorter[TargetDef]:
        # We want to create each `TargetDef` along with its dependencies also as
        # `TargetDef`s, so we need a depedency graph to construct the defs before
        # we can build a dependency graph of `TargetDef`s
        builder_graph: TopologicalSorter[str] = TopologicalSorter()
        self._build_doc_dep_graph(target_name, builder_graph, visited=set())
        try:
            builder_graph.prepare()
        except CycleError as exc:
            cycle_nodes = " -> ".join((node for node in exc.args[1]))
            logger.exception(f"Target dependencies are cyclical: {cycle_nodes}")
            raise

        graph: TopologicalSorter[TargetDef] = TopologicalSorter()
        def_map: dict[str, TargetDef] = {}
        while builder_graph.is_active():
            for target_name in builder_graph.get_ready():
                builder_graph.done(target_name)
                target_doc = self.target_docs[target_name]

                if target_doc.model_extra:
                    component_defs = [
                        ComponentDef(
                            name=key,
                            cls=self.component_types[key],
                            args=values,  # type: ignore
                        )
                        for (key, values) in target_doc.model_extra.items()
                        if isinstance(values, dict)
                    ]
                else:
                    component_defs = []

                target_def = TargetDef(
                    name=target_name,
                    path=target_doc.path,
                    dependencies={
                        def_map[sub_dep_name]
                        for sub_dep_name in target_doc.target.dependencies or []
                    },
                    component_defs=component_defs,
                )

                def_map[target_name] = target_def
                graph.add(target_def, *target_def.dependencies)

        graph.prepare()  # since we built in order, this should never fail
        return graph

    def _build_doc_dep_graph(
        self, target_name: str, graph: TopologicalSorter[str], visited: set[str]
    ):
        if target_name in visited:
            return
        visited.add(target_name)

        if not (target_doc := self.target_docs.get(target_name)):
            raise ValueError(f"No target named '{target_name}' exists")
        graph.add(target_name, *target_doc.target.dependencies or [])
        for dependency in target_doc.target.dependencies or []:
            self._build_doc_dep_graph(
                target_name=dependency, graph=graph, visited=visited
            )


def _determine_names(docs_list: list[TargetDoc]) -> dict[str, TargetDoc]:
    docs_dict: dict[str, TargetDoc] = {}
    conflicts: list[str] = []

    for doc in docs_list:
        name = _determine_name(doc)
        if name in docs_dict:
            conflicts.append(
                f"Target with name '{name}' defined in both "
                f"{doc.path} and {docs_dict[name].path}"
            )
        else:
            docs_dict[name] = doc

    if conflicts:
        raise TargetErrors(target_name_conflicts=conflicts)
    return docs_dict


def _determine_name(doc: TargetDoc) -> str:
    if doc.target.name:
        return doc.target.name
    return doc.path.name[0 : -(len(doc.path.suffix))]


def _deserialize_target_docs(target_dirs: Iterable[Path]) -> list[TargetDoc]:
    target_docs: list[TargetDoc] = []
    errors: list[str] = []
    for target_dir in target_dirs:
        if not target_dir.exists():
            logger.warn(f"Target directory {target_dir} does not exist")
        elif not target_dir.is_dir():
            logger.warn(f"Target directory {target_dir} is not a directory")
        else:
            logger.debug(f"Searching {target_dir} for targets")
            try:
                target_docs.extend(_search_target_dir(target_dir))
            except TargetErrors as exc:
                errors.extend(exc.invalid_target_messages)

    if errors:
        raise TargetErrors(invalid_target_messages=errors)
    return target_docs


def _search_target_dir(target_dir: Path) -> list[TargetDoc]:
    target_docs: list[TargetDoc] = []
    errors: list[str] = []

    for toml in (
        child
        for child in target_dir.iterdir()
        if child.is_file() and child.name.endswith(".toml")
    ):
        try:
            with toml.open("rb") as fp:
                target_docs.append(TargetDoc(path=toml, **tomllib.load(fp)))
        except ValidationError as exc:
            errors.extend((error["msg"] for error in exc.errors()))

    if errors:
        raise TargetErrors(invalid_target_messages=errors)
    return target_docs
