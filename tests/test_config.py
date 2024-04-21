from __future__ import annotations

import io
from itertools import cycle
from pathlib import Path
from typing import TYPE_CHECKING, Callable
import pytest
from overrun.config import Config, ConfigFailed, ConfigOptions

if TYPE_CHECKING:
    from .conftest import cd_t, mkdir_t, sibling_t


def test_default_not_in_project(tmp_path: Path, cd: cd_t):
    with cd(tmp_path):
        config = Config.attempt_init()
    assert isinstance(config, ConfigFailed)
    assert config.cause == ConfigFailed.Cause.NotInProject
    assert config.options == ConfigOptions()


def test_default_in_project(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.attempt_init()

    assert isinstance(config, Config)
    assert config.current_working_project == cwp
    assert config.projects == {cwp}
    assert config.target_directories == {
        cwp: {cwp / ".overrun/targets"},
    }


def test_default_siblings(cwp: Path, cd: cd_t, sibling: sibling_t):
    sib1 = sibling("sib1")
    sib2 = sibling("sib2")
    with cd(cwp):
        config = Config.attempt_init()

    assert isinstance(config, Config)
    assert config.projects == {cwp, sib1, sib2}
    assert config.target_directories == {
        cwp: {cwp / ".overrun/targets"},
        sib1: {sib1 / ".overrun/targets"},
        sib2: {sib2 / ".overrun/targets"},
    }


def test_default_false_siblings(
    tmp_path: Path, mkdir: mkdir_t, cwp: Path, cd: cd_t, sibling: sibling_t
):
    sib1 = sibling("sib1")
    with cd(tmp_path):
        mkdir(
            "sib2/.not-overrun/targets",
            "sib3/.git/targets",
        )
    with cd(cwp):
        config = Config.attempt_init()

    assert isinstance(config, Config)
    assert config.projects == {cwp, sib1}
    assert config.target_directories == {
        cwp: {cwp / ".overrun/targets"},
        sib1: {sib1 / ".overrun/targets"},
    }


def test_default_custom_siblings(tmp_path: Path, mkdir: mkdir_t, cwp: Path, cd: cd_t):
    with cd(tmp_path):
        mkdir(
            "foo/sib/.overrun/targets",
            "bar/sib/.overrun/targets",
            "baz/sib/.overrun/targets",
        )
    with cd(cwp):
        config = Config.attempt_init(
            config_file=io.BytesIO(b"""
            [patterns]
            siblings = ["../foo/*", "../bar/*"]
        """)
        )

    sib1 = (tmp_path / "foo/sib").resolve()
    sib2 = (tmp_path / "bar/sib").resolve()

    assert isinstance(config, Config)
    assert config.projects == {cwp, sib1, sib2}
    assert config.target_directories == {
        cwp: {cwp / ".overrun/targets"},
        sib1: {sib1 / ".overrun/targets"},
        sib2: {sib2 / ".overrun/targets"},
    }


@pytest.fixture
def test_cwp_determination_with(
    tmp_path: Path, mkdir: mkdir_t, cd: cd_t
) -> Callable[[list[str], list[str], Callable[[], Config | ConfigFailed]], None]:
    def inner(
        indicators: list[str],
        red_herrings: list[str],
        config_init: Callable[[], Config | ConfigFailed],
    ):
        indicator = cycle(iter(indicators))
        red_herring = cycle(iter(red_herrings))

        with cd(tmp_path):
            mkdir(
                f"{next(indicator)}",
                f"foo/{next(indicator)}",
                "foo/bar",
                f"foo/bar/{next(red_herring)}",
                f"foo/bar/baz/{next(red_herring)}",
                f"foo/bar/baz/foo/{next(indicator)}",
            )

        for cd_to, expect in [
            (".", "."),
            ("foo", "foo"),
            ("foo/bar", "foo"),
            ("foo/bar/baz", "foo"),
            ("foo/bar/baz", "foo"),
            ("foo/bar/baz/foo", "foo/bar/baz/foo"),
        ]:
            with cd(tmp_path / cd_to):
                config = config_init()
                assert isinstance(config, Config)
                cwp = config.current_working_project
                assert cwp.resolve() == Path(tmp_path / expect).resolve()

    return inner


def test_cwp(
    test_cwp_determination_with: Callable[
        [list[str], list[str], Callable[[], Config | ConfigFailed]], None
    ],
):
    test_cwp_determination_with(
        [".overrun"],
        [".git", ".foo"],
        Config.attempt_init,
    )


def test_cwp_custom_project_indicators(
    test_cwp_determination_with: Callable[
        [list[str], list[str], Callable[[], Config | ConfigFailed]], None
    ],
):
    def config_init() -> Config | ConfigFailed:
        file = io.BytesIO(b"""
            [patterns]
            projects = [".git", ".project"]
        """)
        return Config.attempt_init(config_file=file)

    test_cwp_determination_with(
        [".git", ".project"],
        [".overrun"],
        config_init,
    )


def test_target_directories(tmp_path: Path, cd: cd_t, cwp: Path, mkdir: mkdir_t):
    with cd(tmp_path):
        mkdir(
            "sib1/.overrun/targets",
            "sib2/.overrun/not-targets",
        )
    with cd(cwp):
        config = Config.attempt_init()

    sib1 = (tmp_path / "sib1").resolve()

    assert isinstance(config, Config)
    assert config.target_directories == {
        cwp: {cwp / ".overrun/targets"},
        sib1: {sib1 / ".overrun/targets"},
    }


def test_custom_target_directories(tmp_path: Path, cd: cd_t, cwp: Path, mkdir: mkdir_t):
    with cd(tmp_path):
        mkdir(
            "sib1/.overrun/testgets",
            "sib1/.overrun/tarjets",
            "sib2/.overrun/targets",
        )
    with cd(cwp):
        config = Config.attempt_init(
            config_file=io.BytesIO(b"""
            [patterns]
            target_directories = [".overrun/testgets", ".overrun/tarjets"]
        """)
        )

    sib1 = (tmp_path / "sib1").resolve()

    assert isinstance(config, Config)
    assert config.target_directories == {
        sib1: {
            sib1 / ".overrun/testgets",
            sib1 / ".overrun/tarjets",
        },
    }
