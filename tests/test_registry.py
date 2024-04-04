from __future__ import annotations

from graphlib import CycleError
from pathlib import Path
import pytest
from conftest import cd_t, mkdir_t
from overrun.components.exec import Exec
from overrun.config import Config
from overrun.exceptions import TargetErrors
from overrun.registry import Registry


@pytest.fixture
def target_one(cwp: Path):
    with (cwp / ".overrun/targets/one.toml").open("wb+") as fp:
        fp.write(b"""
        [exec]
        cwd = "subdir"
        argv = ["sleep", "1"]
        """)


@pytest.fixture
def target_one_name_conflict(cwp: Path, mkdir: mkdir_t):
    mkdir(cwp / "../sib1/.overrun/targets")
    with (cwp / "../sib1/.overrun/targets/one.toml").resolve().open("wb+") as fp:
        fp.write(b"")


@pytest.fixture
def target_two(cwp: Path):
    with (cwp / ".overrun/targets/two.toml").open("wb+") as fp:
        fp.write(b"")


@pytest.fixture
def target_two_name_conflict(cwp: Path, mkdir: mkdir_t):
    mkdir(cwp / "../sib2/.overrun/targets")
    with (cwp / "../sib2/.overrun/targets/two.toml").resolve().open("wb+") as fp:
        fp.write(b"")


@pytest.fixture
def target_three_invalid(cwp: Path):
    with (cwp / ".overrun/targets/three.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            name = {}
        """)


@pytest.fixture
def target_a(cwp: Path):
    with (cwp / ".overrun/targets/a.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = ["b"]
        """)


@pytest.fixture
def target_b(cwp: Path):
    with (cwp / ".overrun/targets/b.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = ["c"]
        """)


@pytest.fixture
def target_c(cwp: Path):
    with (cwp / ".overrun/targets/c.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = []
        """)


@pytest.fixture
def target_x_depends_y(cwp: Path):
    with (cwp / ".overrun/targets/x.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = ["y"]
        """)


@pytest.fixture
def target_y_depends_z(cwp: Path):
    with (cwp / ".overrun/targets/y.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = ["z"]
        """)


@pytest.fixture
def target_z_depends_x(cwp: Path):
    with (cwp / ".overrun/targets/z.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            dependencies = ["x"]
        """)


@pytest.fixture
def target_four_invalid(cwp: Path):
    with (cwp / ".overrun/targets/four.toml").open("wb+") as fp:
        fp.write(b"""
            [target]
            name = {}
        """)


@pytest.mark.usefixtures("target_one", "target_two")
def test_registry_target_doc_collection(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.find_or_default()
    registry = Registry(target_dirs=config.target_directories)
    assert len(registry.target_docs) == 2
    assert registry.target_docs["one"]
    assert registry.target_docs["two"]


@pytest.mark.usefixtures(
    "target_one", "target_one_name_conflict", "target_two", "target_two_name_conflict"
)
def test_registry_target_doc_raises_name_collision(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.find_or_default()
    with pytest.raises(TargetErrors) as excinfo:
        Registry(target_dirs=config.target_directories)
    exc: TargetErrors = excinfo.value
    assert not exc.invalid_target_messages
    assert len(exc.target_name_conflicts) == 2


@pytest.mark.usefixtures("target_three_invalid", "target_four_invalid")
def test_registry_target_doc_raises_name_invalid(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.find_or_default()
    with pytest.raises(TargetErrors) as excinfo:
        Registry(target_dirs=config.target_directories)
    exc: TargetErrors = excinfo.value
    assert len(exc.invalid_target_messages) == 2
    assert not exc.target_name_conflicts


@pytest.mark.usefixtures("target_a", "target_b", "target_c")
def test_registry_dependency_graph(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.find_or_default()
    registry = Registry(target_dirs=config.target_directories)
    graph = registry.depedency_graph(target_name="a")

    expect = iter(["c", "b", "a"])
    while graph.is_active():
        for node in graph.get_ready():
            assert node.name == next(expect)
            graph.done(node)

    with pytest.raises(StopIteration):
        next(expect)


@pytest.mark.usefixtures(
    "target_x_depends_y", "target_y_depends_z", "target_z_depends_x"
)
def test_registry_dependency_graph_cycle(cwp: Path, cd: cd_t):
    with cd(cwp):
        config = Config.find_or_default()
    registry = Registry(target_dirs=config.target_directories)
    with pytest.raises(CycleError):
        registry.depedency_graph(target_name="x")


@pytest.mark.usefixtures("target_one")
def test_component_doc_collection(cd: cd_t, cwp: Path):
    with cd(cwp):
        config = Config.find_or_default()
    registry = Registry(target_dirs=config.target_directories)
    graph = registry.depedency_graph(target_name="one")
    (target_def,) = graph.get_ready()
    assert len(target_def.component_defs) == 1
    assert target_def.component_defs[0].name == "exec"
    assert target_def.component_defs[0].cls is Exec
    assert target_def.component_defs[0].args == {
        "cwd": "subdir",
        "argv": ["sleep", "1"],
    }
