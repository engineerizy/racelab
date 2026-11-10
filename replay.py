"""Run named checkpoints in a recorded order across Python async workflows."""

import asyncio
import json
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar("T")


class ReplayError(RuntimeError):
    """The workflows could not complete the supplied schedule."""


@dataclass(frozen=True, slots=True)
class TraceEntry:
    checkpoint: str
    outcome: str


def load_schedule(path: Path) -> tuple[str, ...]:
    checkpoints = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(checkpoints, list) or not all(
        isinstance(checkpoint, str) and checkpoint for checkpoint in checkpoints
    ):
        raise ReplayError(f"{path.name} must contain a JSON list of checkpoint names.")
    return tuple(checkpoints)


class Replay:
    def __init__(self, schedule: Sequence[str]):
        self._schedule = tuple(schedule)
        self._positions = {name: index for index, name in enumerate(self._schedule)}
        if not self._schedule:
            raise ReplayError("A replay needs at least one checkpoint.")
        if len(self._positions) != len(self._schedule):
            raise ReplayError("Checkpoint names must be unique within a schedule.")
        self._timeline: list[TraceEntry] = []
        self._turn_changed = asyncio.Condition()

    @property
    def next_checkpoint(self) -> str | None:
        index = len(self._timeline)
        return self._schedule[index] if index < len(self._schedule) else None

    @property
    def trace(self) -> tuple[TraceEntry, ...]:
        return tuple(self._timeline)

    async def step(self, actor: str, name: str, action: Callable[[], T]) -> T:
        """Wait for this checkpoint, then run and record one synchronous action."""
        checkpoint = f"{actor}.{name}"
        index = self._positions.get(checkpoint)
        if index is None:
            raise ReplayError(f"Checkpoint {checkpoint} is absent from the schedule.")

        async with self._turn_changed:
            await self._turn_changed.wait_for(lambda: len(self._timeline) >= index)
            if len(self._timeline) > index:
                raise ReplayError(f"Checkpoint {checkpoint} already ran.")

            outcome = action()
            self._timeline.append(TraceEntry(checkpoint, str(outcome)))
            self._turn_changed.notify_all()
            return outcome


Workflow = Callable[[Replay, str], Coroutine[Any, Any, None]]


async def run_replay(
    schedule: Sequence[str], workflows: Mapping[str, Workflow], *, timeout: float = 5.0
) -> tuple[TraceEntry, ...]:
    replay = Replay(schedule)
    tasks: list[asyncio.Task[None]] = []
    deadline = asyncio.timeout(timeout)
    try:
        async with deadline:
            for actor, workflow in workflows.items():
                task = asyncio.create_task(workflow(replay, actor), name=actor)
                tasks.append(task)
            await asyncio.gather(*tasks)
    except TimeoutError as error:
        if not deadline.expired():
            raise
        waiting_for = replay.next_checkpoint or "the workflows to finish"
        raise ReplayError(f"Replay timed out waiting for {waiting_for}.") from error
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if replay.next_checkpoint is not None:
        raise ReplayError(f"Replay ended before checkpoint {replay.next_checkpoint}.")
    return replay.trace
