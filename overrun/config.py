from __future__ import annotations

import glob
import itertools
import logging
import os
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePath
from typing import Self, BinaryIO
import pydantic

ENV_CONFIG_PATH = "OVERRUN_CONFIG"
logger = logging.getLogger(__name__)


class Patterns(pydantic.BaseModel):
    """Patterns used to determine which directories are projects, and locate targets."""

    # Project indicators - A directory containing at least a child matching one
    # of the the indicators is determined to be the project's root. This is used
    # for finding both the current working project, and all sibling projects.
    projects: list[Path] = pydantic.Field(default_factory=lambda: [Path(".overrun")])

    # Sibling patterns - Places to search for sibling projects. All patterns are
    # glob expanded, and each expansion checked for a project root indicator.
    # Relative paths are expanded with `Path.glob` and are relative to the current
    # working project. Absolute paths are expanded with `glob.glob`.
    siblings: list[str] = pydantic.Field(default_factory=lambda: ["../*"])

    # Target directory patterns - Directories to search for targets. Relative paths
    # are relative to the current working project, and all sibling projects.
    target_directories: list[Path] = pydantic.Field(
        default_factory=lambda: [Path(".overrun/targets")]
    )


class ConfigOptions(pydantic.BaseModel):
    """Model through which the configuration file (if any) is deserialized.

    This is the definitive source of information on what keys are valid in the
    configuration file, and what default values for each are used when not defined.
    """

    patterns: Patterns = pydantic.Field(default_factory=Patterns)


@dataclass
class Config:
    """Configuration options and all derived values determined at runtime."""

    pwd: Path
    options: ConfigOptions

    target_directories: dict[Path, set[Path]]  # project dirs mapped to targets within
    current_working_project: Path
    sibling_projects: set[Path]
    projects: set[Path]

    @classmethod
    def attempt_init(
        cls: type[Self],
        *,
        config_file: Path | BinaryIO | None = None,
    ) -> Self | ConfigFailed:
        # map `config_file` to a dict of config_values to override defaults
        config_values = {}
        match config_file:
            case Path():
                path = _config_file_search(explicit_path=config_file)
                if isinstance(path, ConfigFailed):
                    return path

                if path:
                    try:
                        with path.open("rb") as fp:
                            config_values = tomllib.load(fp)
                    except tomllib.TOMLDecodeError as exc:
                        return ConfigFailed(
                            ConfigFailed.Cause.InvalidToml,
                            additional_context=str(exc),
                        )
                    except Exception as exc:
                        return ConfigFailed(
                            ConfigFailed.Cause.IoError,
                            additional_context=str(exc),
                        )
                        return path
            case None:
                pass
            case _:
                try:
                    config_values = tomllib.load(config_file)
                except tomllib.TOMLDecodeError as exc:
                    return ConfigFailed(
                        ConfigFailed.Cause.InvalidToml,
                        additional_context=str(exc),
                    )

        # get default config options and overlay parsed values
        try:
            options = ConfigOptions(**config_values)
        except pydantic.ValidationError as exc:
            errors = [error["msg"] for error in exc.errors()]
            return ConfigFailed(
                ConfigFailed.Cause.InvalidConfig,
                additional_context=str("\n".join(errors)),
            )

        pwd = Path.cwd().resolve()

        cwp = _cwp(path=pwd, options=options)
        if isinstance(cwp, ConfigFailed):
            return cwp

        try:
            sibling_projects = _sibling_projects(cwp=cwp, options=options)
            projects = {cwp, *sibling_projects}
            target_directories = _target_directories(projects=projects, options=options)

            return cls(
                pwd=pwd,
                current_working_project=cwp,
                options=options,
                sibling_projects=sibling_projects,
                projects=projects,
                target_directories=target_directories,
            )
        except Exception as exc:
            return ConfigFailed(
                ConfigFailed.Cause.IoError,
                additional_context=str(exc),
            )


@dataclass
class ConfigFailed:
    """Context about why a valid `Config` could not be constructed."""

    class Cause(StrEnum):
        EnvPathNotFound = f"{ENV_CONFIG_PATH} points to a file that does not exist"
        ExplicitPathNotFound = "Config flag points to a file that does not exist"
        InvalidToml = "The config file is not valid toml"
        InvalidConfig = "The config is not valid"
        NotInProject = "Not in an overrun project directory"
        IoError = "Failed to read the config file"

    cause: Cause
    additional_context: str | None = None
    options: ConfigOptions | None = None


def _config_file_search(
    explicit_path: Path | None = None,
) -> Path | None | ConfigFailed:
    if env := os.environ.get(ENV_CONFIG_PATH):
        path = Path(env).expanduser()
        if path.exists():
            return Path(env)
        return ConfigFailed(
            cause=ConfigFailed.Cause.EnvPathNotFound,
            additional_context=f"{ENV_CONFIG_PATH} points to {env}",
        )
    if explicit_path:
        path = explicit_path.expanduser()
        if path.exists():
            return explicit_path
        return ConfigFailed(
            cause=ConfigFailed.Cause.ExplicitPathNotFound,
            additional_context=f"Config flag points to {explicit_path}",
        )

    default = Path("~/.config/overrun/config.toml").expanduser()
    return default if default.exists() else None


def _cwp(path: Path, options: ConfigOptions) -> Path | ConfigFailed:
    """The project from which overrun was invoked."""
    if cwp := _recursive_find_project(path, options=options):
        return cwp

    return ConfigFailed(
        cause=ConfigFailed.Cause.NotInProject,
        options=options,
    )


def _has_project_indicator(pwd: Path, *, options: ConfigOptions) -> bool:
    return any((pwd / indicator).exists() for indicator in options.patterns.projects)


def _recursive_find_project(path: Path, *, options: ConfigOptions) -> Path | None:
    root = Path("/")

    while path != root:
        if _has_project_indicator(path, options=options):
            return path
        path = path.parent

    if _has_project_indicator(root, options=options):
        return root

    return None


def _sibling_absolute_expansions(pattern: str, *, cwp: Path) -> set[Path]:
    globbed = (Path(p).resolve() for p in glob.glob(pattern))  # noqa: PTH207
    return {path for path in globbed if path != cwp}


def _sibling_relative_expansions(pattern: str, *, cwp: Path) -> set[Path]:
    return {path for path in cwp.glob(pattern) if path.resolve() != cwp}


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


def _target_directories(
    *, projects: set[Path], options: ConfigOptions
) -> dict[Path, set[Path]]:
    to_check = itertools.product(projects, options.patterns.target_directories)

    target_dirs_set: set[tuple[Path, Path]] = {
        (project, (project / pattern).resolve())
        for (project, pattern) in to_check
        if (project / pattern).is_dir()
    }

    target_dirs: dict[Path, set[Path]] = defaultdict(set)  # type: ignore
    for project, target_dir in target_dirs_set:
        target_dirs[project].add(target_dir)

    return target_dirs
