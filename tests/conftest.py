from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager
import pytest
from pytest_mock import MockerFixture
from overrun.config import ENV_CONFIG_PATH, Config

type cd_t = Callable[[Path | str], ContextManager[Path]]
type mkdir_t = Callable[..., None]
type env_t = Callable[..., None]
type file_config_t = Callable[[str], None]


@pytest.fixture
def env(mocker: MockerFixture) -> env_t:
    def inner(**kwargs: str):
        mocker.patch.dict(os.environ, kwargs)

    return inner


@pytest.fixture
def cd() -> cd_t:
    @contextmanager
    def inner(path: Path | str):
        old = Path.cwd()
        new = Path(path)
        os.chdir(new)
        yield new
        os.chdir(old)

    return inner


@pytest.fixture
def mkdir() -> mkdir_t:
    def inner(*paths: Path | str):
        for path in paths:
            Path(path).resolve().mkdir(parents=True)

    return inner


@pytest.fixture(autouse=True)
def cwp(tmpdir: Path, mkdir: mkdir_t) -> Path:
    mkdir(Path(tmpdir) / "project/.overrun/targets")
    return Path(tmpdir) / "project"


@pytest.fixture
def default_config(cwp: Path) -> Config:  # noqa: ARG001
    return Config.find_or_default()


@pytest.fixture
def file_config(cwp: Path, env: env_t) -> file_config_t:
    def inner(contents: str):
        config_path = cwp / ".overrun.toml"
        env(**{ENV_CONFIG_PATH: str(config_path)})
        with config_path.open("w+") as fp:
            fp.write(contents)

    return inner
