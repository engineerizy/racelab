"""Replay two agents editing the same support ticket from an old snapshot."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, replace

from replay import Replay, TraceEntry, run_replay


@dataclass(frozen=True, slots=True)
class Ticket:
    status: str
    assignee: str
    version: int

    def __str__(self) -> str:
        return f"{self.status}, assigned to {self.assignee}, version {self.version}"


@dataclass(frozen=True, slots=True)
class TicketRun:
    trace: tuple[TraceEntry, ...]
    ticket: Ticket

    @property
    def invariant_holds(self) -> bool:
        # Both agents in this scenario loaded version zero.
        return self.ticket.version == 1

    @property
    def summary(self) -> str:
        return f"Final ticket state is {self.ticket}."


def save_ticket(db: sqlite3.Connection, edited: Ticket, *, fixed: bool) -> str:
    sql = (
        "UPDATE tickets SET status = ?, assignee = ?, version = version + 1 "
        "WHERE id = 1"
    )
    values = (edited.status, edited.assignee)
    if fixed:
        sql += " AND version = ?"
        values += (edited.version,)

    with db:
        updated = db.execute(sql, values)
    return "Saved" if updated.rowcount == 1 else "Conflict. Reload the ticket."


async def run(schedule: Sequence[str], *, fixed: bool) -> TicketRun:
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript(
            """
            CREATE TABLE tickets (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                assignee TEXT NOT NULL,
                version INTEGER NOT NULL
            );
            INSERT INTO tickets VALUES (1, 'Open', 'nobody', 0);
            """
        )
        db.commit()

        def load_ticket() -> Ticket:
            row = db.execute(
                "SELECT status, assignee, version FROM tickets WHERE id = 1"
            ).fetchone()
            return Ticket(*row)

        async def edit_ticket(replay: Replay, agent: str) -> None:
            snapshot = await replay.step(agent, "load_ticket", load_ticket)
            if agent == "agent-a":
                edited = replace(snapshot, status="Closed")
            else:
                edited = replace(snapshot, assignee="Agent B")
            await replay.step(
                agent, "save_ticket", lambda: save_ticket(db, edited, fixed=fixed)
            )

        trace = await run_replay(schedule, {"agent-a": edit_ticket, "agent-b": edit_ticket})
        return TicketRun(trace, load_ticket())
