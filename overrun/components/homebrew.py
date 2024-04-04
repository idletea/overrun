from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel
from overrun import component

if TYPE_CHECKING:
    from overrun.runtime import Context

logger = logging.getLogger(__name__)


class ArgsDoc(BaseModel):
    packages: list[str]


@component.register
class Homebrew:
    """Ensure homebrew packages are installed."""
    packages: list[str]

    def __init__(self, *, context: Context, **kwargs: Any):  # noqa: ARG002
        self.packages = ArgsDoc(**kwargs).packages

    async def start(self, *, context: Context):
        already_installed: list[str] = []
        to_install: list[str] = []

        for package in self.packages:
            if await check_installed(package):
                already_installed.append(package)
            else:
                to_install.append(package)

        if to_install:
            names = ", ".join(to_install)
            logging.info(
                f"Installing homebrew packages {names} in '{context.target_name}'"
            )
            await self._install(to_install)
        elif already_installed:
            logger.debug(
                f"Hombrew packages already installed in '{context.target_name}'"
            )

    async def _install(self, packages: list[str]):
        async with asyncio.TaskGroup() as tg:
            ps = await tg.create_task(
                asyncio.create_subprocess_exec("brew", "install", *packages)
            )
            status = await ps.wait()
            if status != 0:
                msg = "Failed to install homebrew packages"
                raise RuntimeError(msg)


async def check_installed(package: str) -> bool:
    async with asyncio.TaskGroup() as tg:
        ps = await tg.create_task(
            asyncio.create_subprocess_exec(
                "brew",
                "list",
                package,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )
        status = await ps.wait()
        return status == 0
