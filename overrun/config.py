from __future__ import annotations

import glob
import itertools
import logging
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Self
from pydantic import BaseModel, Field

ENV_CONFIG_PATH = "OVERRUN_CONFIG"
logger = logging.getLogger(__name__)


class Patterns(BaseModel):
    """Patterns used to determine which directories are projects, and locate targets."""

    # Project indicators - A directory containing at least a child matching one
    # of the the indicators is determined to be the project's root. This is used
    # for finding both the current working project, and all sibling projects.
    projects: list[Path] = Field(default_factory=lambda: [Path(".overrun")])

    # Sibling patterns - Places to search for sibling projects. All patterns are
    # glob expanded, and each expansion checked for a project root indicator.
    # Relative paths are expanded with `Path.glob` and are relative to the current
    # working project. Absolute paths are expanded with `glob.glob`.
    siblings: list[str] = Field(default_factory=lambda: ["../*"])

    # Target directory patterns - Directories to search for targets. Relative paths
    # are relative to the current working project, and all sibling projects.
    target_directories: list[Path] = Field(
        default_factory=lambda: [Path(".overrun/targets")]
    )


class ConfigOptions(BaseModel):
    """Model through which the configuration file (if any) is deserialized.

    This is the definitive source of information on what keys are valid in the
    configuration file, and what default values for each are used when not defined.
    """

    patterns: Patterns = Field(default_factory=Patterns)


@dataclass
class Config:
    pwd: Path
    options: ConfigOptions

    target_directories: set[Path]
    current_working_project: Path
    sibling_projects: set[Path]
    projects: set[Path]

    @classmethod
    def find_or_default(cls) -> Self:
        config_file = {}
        if path := _default_config_search():
            with path.open("rb") as fp:
                logging.debug(f"Using config file {path}")
                config_file = tomllib.load(fp)
        options = ConfigOptions(**config_file)

        pwd = Path.cwd().resolve()
        cwp = _cwp(path=pwd, options=options)
        sibling_projects = _sibling_projects(cwp=cwp, options=options)
        projects = {cwp, *sibling_projects}
        target_directories = _target_directories(projects=projects, options=options)

        return cls(
            pwd=pwd,
            options=options,
            current_working_project=cwp,
            sibling_projects=sibling_projects,
            projects=projects,
            target_directories=target_directories,
        )


def _default_config_search() -> Path | None:
    if env := os.environ.get(ENV_CONFIG_PATH):
        path = Path(env).expanduser()
        if path.exists():
            return Path(env)
        raise ValueError(f"{ENV_CONFIG_PATH} is not a file")

    default = Path("~/.config/overrun/config.toml").expanduser()
    return default if default.exists() else None


def _cwp(path: Path, options: ConfigOptions) -> Path:
    """The project from which overrun was invoked."""
    if cwp := _recursive_find_project(path, options=options):
        return cwp
    logger.error(f"Could not locate a current working project from {path}")
    sys.exit(1)


def _target_directories(*, projects: set[Path], options: ConfigOptions) -> set[Path]:
    to_check = itertools.product(projects, options.patterns.target_directories)
    return {
        (project / pattern).resolve()
        for (project, pattern) in to_check
        if (project / pattern).is_dir()
    }


def _sibling_projects(*, cwp: Path, options: ConfigOptions) -> set[Path]:
    """All projects found via `sibling_patterns`."""
    paths_to_check: set[Path] = set()
    for pattern in options.patterns.siblings:
        if PurePath(pattern).is_absolute():
            paths_to_check |= _sibling_absolute_expansions(pattern, cwp=cwp)
        else:
            paths_to_check |= _sibling_relative_expansions(pattern, cwp=cwp)

    return {
        path.resolve()
        for path in paths_to_check
        if _has_project_indicator(path, options=options)
    }


def _recursive_find_project(path: Path, *, options: ConfigOptions) -> Path | None:
    root = Path("/")

    while path != root:
        if _has_project_indicator(path, options=options):
            return path
        path = path.parent

    if _has_project_indicator(root, options=options):
        return root

    return None


def _has_project_indicator(pwd: Path, *, options: ConfigOptions) -> bool:
    return any((pwd / indicator).exists() for indicator in options.patterns.projects)


def _sibling_absolute_expansions(pattern: str, *, cwp: Path) -> set[Path]:
    globbed = (Path(p).resolve() for p in glob.glob(pattern))  # noqa: PTH207
    return {path for path in globbed if path != cwp}


def _sibling_relative_expansions(pattern: str, *, cwp: Path) -> set[Path]:
    return {path for path in cwp.glob(pattern) if path.resolve() != cwp}
