from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Iterable
import click
import rich.table
from rich.logging import RichHandler
from rich.pretty import pprint
import overrun
from overrun.config import Config
from overrun.registry import Registry
from overrun.runtime import Runtime

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        cli()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


def config_logging(*, verbose: bool, quiet: bool) -> None:
    class OverrunDebugOnlyFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.levelno < logging.INFO:
                return record.name.startswith("overrun.")
            return True

    match (verbose, quiet):
        case (True, True):
            raise ValueError("both verbose and quiet output requested")
        case (True, False):
            level = logging.DEBUG
        case (False, True):
            level = logging.WARNING
        case (False, False):
            level = logging.INFO
        case _:
            raise AssertionError("pyright doesn't know this can't happen")

    handler = RichHandler()
    handler.addFilter(OverrunDebugOnlyFilter())
    logging.basicConfig(
        format="%(message)s",
        level=level,
        datefmt="[%X]",
        handlers=[handler],
    )


@dataclass
class ContextObj:
    config: Config
    registry: Registry
    runtime: Runtime


@click.group()
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Avoid output.")
@click.pass_context
def cli(ctx: click.Context, *, verbose: bool, quiet: bool) -> None:
    config_logging(verbose=verbose, quiet=quiet)

    config = Config.find_or_default()
    registry = Registry(target_dirs=config.target_directories)
    runtime = Runtime(config=config, registry=registry)

    ctx.obj = ContextObj(
        config=config,
        registry=registry,
        runtime=runtime,
    )


@cli.command
@click.pass_context
def config(ctx: click.Context):
    config: Config = ctx.obj.config
    pprint(config.__dict__)


@cli.command(name="version")
def version_():
    sys.stdout.write(f"{overrun.__version__}\n")


@cli.group()
@click.pass_context
def component(_ctx: click.Context): ...


@component.command(name="list")
@click.pass_context
def component_list(ctx: click.Context):
    context: ContextObj = ctx.obj
    _output_two_col_table(
        items=(
            (name, str(component_type.__doc__))
            for name, component_type in context.registry.component_types.items()
        ),
    )


@cli.group()
@click.pass_context
def target(_ctx: click.Context): ...


@target.command(name="list")
@click.pass_context
def target_list(ctx: click.Context):
    context: ContextObj = ctx.obj
    _output_two_col_table(
        items=(
            (name, str(target_doc.path))
            for (name, target_doc) in context.registry.target_docs.items()
        )
    )


@target.command(name="run")
@click.argument("target")
@click.pass_context
def target_run(ctx: click.Context, target: str):
    context: ContextObj = ctx.obj
    asyncio.run(context.runtime.run(target_name=target))


def _output_two_col_table(
    *,
    items: Iterable[tuple[str, str]],
    styles: tuple[str, str] = ("bold", "bold magenta"),
):
    table = rich.table.Table(
        box=None,
        show_header=False,
        show_footer=False,
        pad_edge=False,
        highlight=True,
    )
    table.add_column(style=styles[0])
    table.add_column(style=styles[1])
    for a, b in items:
        table.add_row(a, b)

    rich.console.Console().print(table)
