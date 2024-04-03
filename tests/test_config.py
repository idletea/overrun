from __future__ import annotations

from pathlib import Path
import pytest
from conftest import cd_t, file_config_t, mkdir_t
from overrun.config import Config


def test_config_from_file(file_config: file_config_t, cwp: Path, cd: cd_t):
    with cd(cwp):
        file_config("""
            [patterns]
            projects = [".overrun", "foo"]
            siblings = ["../*", "../../*"]
        """)
        config = Config.find_or_default()
    assert [str(pat) for pat in config.options.patterns.projects] == [".overrun", "foo"]
    assert config.options.patterns.siblings == ["../*", "../../*"]


def test_default_cwp_discovery(tmpdir: Path, mkdir: mkdir_t, cd: cd_t):
    with cd(tmpdir):
        mkdir(
            ".overrun",
            "foo/.overrun",
            "foo/bar",
            "foo/bar/baz",
            "foo/bar/baz/foo/.overrun",
        )

    for cd_to, expect in [
        (".", "."),
        ("foo", "foo"),
        ("foo/bar", "foo"),
        ("foo/bar/baz", "foo"),
        ("foo/bar/baz", "foo"),
        ("foo/bar/baz/foo", "foo/bar/baz/foo"),
    ]:
        with cd(tmpdir / cd_to):
            cwp = Config.find_or_default().current_working_project
            assert cwp.resolve() == Path(tmpdir / expect).resolve()


def test_custom_cwp_discovery(
    tmpdir: Path,
    file_config: file_config_t,
    mkdir: mkdir_t,
    cd: cd_t,
):
    with cd(tmpdir):
        mkdir(
            "foo/bar/.git",
            "foo/bar/baz/.foo",
            "foo/bar/baz/foo/bar",
        )

    for cd_to, expect in [
        ("foo/bar/baz", "foo/bar/baz"),
        ("foo/bar", "foo/bar"),
        ("foo/bar/baz/foo/bar", "foo/bar/baz"),
    ]:
        with cd(tmpdir / cd_to):
            file_config("""
                [patterns]
                projects = [".foo", ".git"]
            """)
            config = Config.find_or_default()
            actual = config.current_working_project.resolve()
            assert str(actual) == str(Path(tmpdir / expect).resolve())


def test_cwp_discovery_raises(cd: cd_t):
    with cd("/tmp"), pytest.raises(SystemExit):
        _ = Config.find_or_default()


def test_default_sibling_discovery(mkdir: mkdir_t, cd: cd_t, cwp: Path):
    with cd(cwp / ".."):
        mkdir(
            "sib1/.overrun",
            "sib2/.overrun",
            "notsib/.not-overrun",
        )

    with cd(cwp):
        config = Config.find_or_default()

    assert sorted([str(path) for path in config.sibling_projects]) == [
        str((cwp / "../sib1").resolve()),
        str((cwp / "../sib2").resolve()),
    ]
    assert sorted([str(path) for path in config.projects]) == [
        str(cwp.resolve()),
        str((cwp / "../sib1").resolve()),
        str((cwp / "../sib2").resolve()),
    ]


def test_custom_sibling_discovery(
    file_config: file_config_t, cd: cd_t, cwp: Path, mkdir: mkdir_t
):
    with cd(cwp / ".."):
        mkdir(
            "sib1/.overrun",
            "notme",
            "foo/sib2/.overrun",
            "foo/notme",
        )

    with cd(cwp):
        file_config("""
            [patterns]
            siblings = ["../*", "../foo/*"]
        """)
        config = Config.find_or_default()

    assert sorted([str(path) for path in config.sibling_projects]) == [
        str((cwp / "../foo/sib2").resolve()),
        str((cwp / "../sib1").resolve()),
    ]
    assert sorted([str(path) for path in config.projects]) == [
        str((cwp / "../foo/sib2").resolve()),
        str(cwp.resolve()),
        str((cwp / "../sib1").resolve()),
    ]


def test_default_target_directories_discovery(cd: cd_t, cwp: Path, mkdir: mkdir_t):
    with cd(cwp / ".."):
        mkdir(
            "sib1/.overrun/targets",
            "sib2/.overrun/not-targets",
        )

    with cd(cwp):
        config = Config.find_or_default()

    assert sorted([str(path) for path in config.target_directories]) == [
        str((cwp / ".overrun/targets").resolve()),
        str((cwp / "../sib1/.overrun/targets").resolve()),
    ]


def test_custom_target_directories_discovery(
    file_config: file_config_t, cd: cd_t, cwp: Path, mkdir: mkdir_t
):
    with cd(cwp / ".."):
        mkdir(
            "project/targets",
            "sib1/targets",
            "sib1/.overrun",
            "sib2/not-targets",
            "sib2/.overrun",
        )

    with cd(cwp):
        file_config("""
            [patterns]
            target_directories = ["targets"]
        """)
        config = Config.find_or_default()

    assert sorted([str(path) for path in config.target_directories]) == [
        str((cwp / "targets").resolve()),
        str((cwp / "../sib1/targets").resolve()),
    ]
