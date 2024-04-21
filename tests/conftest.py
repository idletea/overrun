from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager
import pytest

type cd_t = Callable[[Path | str], ContextManager[Path]]
type mkdir_t = Callable[..., None]
type sibling_t = Callable[[str], Path]


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


@pytest.fixture
def cwp(tmp_path: Path, mkdir: mkdir_t) -> Path:
    mkdir(tmp_path / "project/.overrun/targets")
    return tmp_path / "project"


@pytest.fixture
def sibling(tmp_path: Path, mkdir: mkdir_t) -> sibling_t:
    def inner(path: str) -> Path:
        path_ = tmp_path / path
        mkdir(path_ / ".overrun/targets")
        return path_

    return inner
