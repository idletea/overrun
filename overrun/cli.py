from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
import click
from rich.logging import RichHandler
import overrun
from overrun.app import AppBuilder

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        cli()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


def config_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    class OverrunDebugOnlyFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.levelno < logging.INFO:
                return record.name.startswith("overrun.")
            return True

    handler = RichHandler()
    handler.addFilter(OverrunDebugOnlyFilter())
    logging.basicConfig(
        format="%(message)s",
        level=level,
        datefmt="[%X]",
        handlers=[handler],
    )


@dataclass
class CtxObj:
    app_builder: AppBuilder


@click.group()
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output.")
@click.pass_context
def cli(ctx: click.Context, *, verbose: bool) -> None:
    config_logging(verbose=verbose)
    ctx.obj = CtxObj(app_builder=AppBuilder())


@cli.command(help="Current version of overrun")
def version():
    sys.stdout.write(f"{overrun.__version__}\n")


@cli.command(help="Information to help debug")
@click.pass_context
def doctor(ctx: click.Context):
    context: CtxObj = ctx.obj
    context.app_builder.doctor()


@cli.command(help="Output a toml document of the loaded configuration")
@click.pass_context
def config(ctx: click.Context):
    context: CtxObj = ctx.obj
    context.app_builder.dump_config()
