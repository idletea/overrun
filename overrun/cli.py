from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
import click
from rich.logging import RichHandler
from rich.pretty import pprint
import overrun
from overrun.config import Config

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
class ClickContext:
    config: Config


@click.group()
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Avoid output.")
@click.pass_context
def cli(ctx: click.Context, *, verbose: bool, quiet: bool) -> None:
    config_logging(verbose=verbose, quiet=quiet)
    ctx.obj = ClickContext(config=Config.find_or_default())


@cli.command
@click.pass_context
def config(ctx: click.Context) -> None:
    config: Config = ctx.obj.config
    pprint(config.__dict__)


@cli.command(name="version")
def version_() -> None:
    sys.stdout.write(f"{overrun.__version__}\n")
