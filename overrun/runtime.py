from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack, contextmanager, suppress
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Generator
from overrun.config import Config
from overrun.registry import Registry
from overrun.target import Target
from overrun.types import TargetDef

logger = logging.getLogger(__name__)


@dataclass
class EventNewOutputStream:
    """A component attached a new output stream."""

    name: str
    reader: asyncio.StreamReader


@dataclass(frozen=True, slots=True)
class Context:
    target_name: str
    cwd: Path  # directory in which the target is defined
    cwp: Path  # project directory in which overrun was run
    event_queue: asyncio.Queue[EventNewOutputStream]


@dataclass(frozen=True, slots=True)
class Runtime:
    config: Config
    registry: Registry

    _contexts: dict[Target, Context] = field(default_factory=dict)
    _targets: list[Target] = field(default_factory=list)
    _event_queue: asyncio.Queue[EventNewOutputStream] = field(
        default_factory=asyncio.Queue
    )

    async def run(self, *, target_name: str):
        """Run a target and all its dependencies from start to completion."""
        target_graph = self.registry.depedency_graph(target_name=target_name)
        await self._run(target_graph=target_graph)

    async def _run(self, *, target_graph: TopologicalSorter[TargetDef]):
        async with AsyncExitStack() as stack:
            stop_event = stack.enter_context(_catch_stop_signal())
            tg = await stack.enter_async_context(asyncio.TaskGroup())

            stop_signal = tg.create_task(stop_event.wait())
            process_events = tg.create_task(self._process_events())
            lifecycle = tg.create_task(self._lifecycle(target_graph=target_graph))

            done, _pending = await asyncio.wait(
                (stop_signal, process_events, lifecycle),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if process_events not in done:
                process_events.cancel()

            if stop_signal not in done:
                stop_signal.cancel()

            if lifecycle not in done:
                logger.info("Caught stop signal - stopping targets")
                lifecycle.cancel()

    async def _lifecycle(self, *, target_graph: TopologicalSorter[TargetDef]):
        # we don't stop components if they never started their run, so
        # this belongs outside the guard to stop on task cancellation
        await self._lifecycle_start(target_graph=target_graph)

        try:
            await self._lifecycle_run()
        except asyncio.CancelledError:
            logger.debug("Caught stop signal - cancelling running targets and stopping")
            await self._lifecycle_stop()
        else:
            logger.debug("All targets completed running - now stopping all targets")
            await self._lifecycle_stop()
        logger.info("All targets stopped")

    async def _lifecycle_start(self, *, target_graph: TopologicalSorter[TargetDef]):
        async with asyncio.TaskGroup() as tg:
            target_starts: dict[asyncio.Task[None], tuple[TargetDef, Target]] = {}

            while target_graph.is_active() or target_starts:
                target_defs = target_graph.get_ready()
                for target_def in target_defs:
                    context = Context(
                        target_name=target_def.name,
                        cwd=target_def.path.parent,
                        cwp=self.config.current_working_project,
                        event_queue=self._event_queue,
                    )

                    target = Target.from_target_def(
                        target_def=target_def, context=context
                    )

                    if target.startable:
                        logging.info(f"Starting target '{target.name}'")
                        start_task = tg.create_task(target.start(context=context))
                        target_starts[start_task] = target_def, target
                    else:
                        target_graph.done(target_def)
                        logging.debug(f"No start defined for target '{target.name}'")

                    self._contexts[target] = context

                # after queueing as many targets starts as we can, wait for the
                # next start to complete so we can potentially start more targets
                #
                # may raise a `ValueError` if target_starts is empty due to targets
                # without a `start` method not being appended to target_starts
                with suppress(ValueError):
                    done, _ = await asyncio.wait(
                        target_starts.keys(), return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        target_def, target = target_starts[task]
                        logger.debug(f"Finished start of '{target.name}'")
                        self._targets.append(target)
                        del target_starts[task]
                        target_graph.done(target_def)

            assert not target_starts  # the above should drive all starts to completion

    async def _lifecycle_run(self):
        async with asyncio.TaskGroup() as tg:
            running: dict[asyncio.Task[None], Target] = {}
            runable = [target for target in self._targets if target.runable]
            for target in runable:
                task = tg.create_task(target.run(context=self._contexts[target]))
                running[task] = target

            while running:
                done, _ = await asyncio.wait(
                    running.keys(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    target = running[task]
                    del running[task]
                    logger.info(f"Run completed for '{target.name}'")

            assert not running  # the above should drive all runs to completion

    async def _lifecycle_stop(self):
        async with asyncio.TaskGroup() as tg:
            stopping: dict[asyncio.Task[None], Target] = {}
            stopable = [target for target in reversed(self._targets) if target.stopable]
            for target in stopable:
                task = tg.create_task(target.stop(context=self._contexts[target]))
                stopping[task] = target

            while stopping:
                done, _ = await asyncio.wait(
                    stopping.keys(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    target = stopping[task]
                    del stopping[task]
                    logger.info(f"Stop completed for '{target.name}'")

            assert not stopping  # the above should drive all stops to completion

    async def _process_events(self):
        """Placeholder for handling events components may issue back to the runtime."""
        await asyncio.sleep(sys.maxsize)


@contextmanager
def _catch_stop_signal() -> Generator[asyncio.Event, None, None]:
    stop_signals = (signal.SIGINT, signal.SIGTERM)
    stop_signal = asyncio.Event()
    loop = asyncio.get_running_loop()

    def set_stop_signal():
        logger.debug("Caught stop signal - setting event to notify runtime")
        stop_signal.set()

    for sig in stop_signals:
        loop.add_signal_handler(sig, set_stop_signal)
    logger.debug("Installed signal handlers")

    yield stop_signal

    for sig in stop_signals:
        loop.remove_signal_handler(sig)
    logger.debug("Uninstalled signal handlers")
