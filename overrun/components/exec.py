from __future__ import annotations

import os
import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, BinaryIO
from pydantic import BaseModel, conlist
from overrun import component

if TYPE_CHECKING:
    from overrun.runtime import Context

logger = logging.getLogger(__name__)


class ArgsDoc(BaseModel):
    argv: Annotated[list[str], conlist(str, min_length=1)]
    cwd: Path | None = None  # resolved relative to cwp
    env: dict[str, str] | None = None
    output_file: Path | None = None


@component.register
class Exec:
    """Exec arbitrary processes."""

    args: ArgsDoc
    cwd: Path
    ps: asyncio.subprocess.Process | None
    output_buf: BinaryIO

    def __init__(self, *, context: Context, **kwargs: Any):
        self.args = ArgsDoc(**kwargs)
        self.cwd = (context.cwd / self.args.cwd) if self.args.cwd else context.cwd
        self.proc = None

        if self.args.output_file:
            path = self.cwd / self.args.output_file
            if not path.parent.exists():
                logger.debug(
                    f"Creating dir to contain the output_file "
                    f"in '{context.target_name}'"
                )
                path.parent.mkdir(parents=True)
            self.output_buf = path.open("wb")
        else:
            self.output_buf = Path("/dev/stdout").open("wb")  # noqa: SIM115

    async def start(self, *, context: Context):
        logging.debug(
            f"Spawning '{self.args.argv[0]}' process in '{context.target_name}'"
        )

        env = self.args.env
        if env and "PATH" not in env:
            env["PATH"] = os.environ.get("PATH")

        self.ps = await asyncio.create_subprocess_exec(
            self.args.argv[0],
            *self.args.argv[1:],
            cwd=self.cwd,
            env=env,
            stderr=asyncio.subprocess.STDOUT,
            stdout=self.output_buf,
        )

    async def run(self, *, context: Context):
        assert self.ps
        status = await self.ps.wait()
        if status == 0:
            logger.debug(
                f"Process '{self.args.argv[0]}' exited successfully "
                f"in '{context.target_name}'"
            )
        else:
            logger.warn(
                f"Process '{self.args.argv[0]}' exited with status {status} "
                f"in '{context.target_name}'"
            )

    async def stop(self, *, context: Context):
        assert self.ps

        # we give a short grace period for short-running program before signalling them
        with suppress(asyncio.TimeoutError):
            async with asyncio.timeout(0.1):
                if nonzero_status := await self.ps.wait():
                    logger.warn(
                        f"Process '{self.args.argv[0]}' exited with "
                        f" status {nonzero_status} "
                        f"in '{context.target_name}'"
                    )
                else:
                    logger.debug(
                        f"Process '{self.args.argv[0]}' exited successfully "
                        f"in '{context.target_name}'"
                    )
                return

        grace_time = 5
        logger.warn(
            f"Sending SIGTERM to '{self.args.argv[0]}' and waiting {grace_time}s "
            f"in '{context.target_name}'"
        )

        try:
            self.ps.terminate()
        except ProcessLookupError:
            # there is a race - the process may die in between
            # us checking if it's dead and trying to signal it
            if nonzero_status := self.ps.returncode:
                logger.warn(
                    f"Process '{self.args.argv[0]}' exited with status {nonzero_status} "
                    f"in '{context.target_name}'"
                )
                return
            logger.debug(
                f"Process '{self.args.argv[0]}' exited with status {nonzero_status} "
                f"in '{context.target_name}'"
            )
        try:
            async with asyncio.timeout(grace_time):
                status = await self.ps.wait()
                if status == 0:
                    logger.debug(
                        f"Process '{self.args.argv[0]}' exited successfully "
                        f"in '{context.target_name}'"
                    )
                else:
                    logger.warn(
                        f"Process '{self.args.argv[0]}' exited with status {status} "
                        f"in '{context.target_name}'"
                    )
        except asyncio.TimeoutError:
            logger.warn(
                f"Timeout waiting for '{self.args.argv[0]}' - sending SIGKILL "
                f"in '{context.target_name}'"
            )
            self.ps.kill()
