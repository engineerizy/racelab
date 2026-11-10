"""Replay two checkouts for the last ticket in stock."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass

from replay import Replay, TraceEntry, run_replay


@dataclass(frozen=True, slots=True)
class BookingRun:
    trace: tuple[TraceEntry, ...]
    buyers: tuple[str, ...]
    remaining: int

    @property
    def invariant_holds(self) -> bool:
        return len(self.buyers) + self.remaining == 1

    @property
    def summary(self) -> str:
        return (
            f"Confirmed bookings for 1 ticket = {len(self.buyers)}. "
            f"Remaining stock = {self.remaining}."
        )


def create_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY,
            remaining INTEGER NOT NULL CHECK (remaining >= 0)
        );
        CREATE TABLE bookings (buyer TEXT NOT NULL PRIMARY KEY);
        INSERT INTO inventory (id, remaining) VALUES (1, 1);
        """
    )
    db.commit()


def reserve_ticket(
    db: sqlite3.Connection, buyer: str, tickets_seen: int, *, fixed: bool
) -> bool:
    # If the booking insert fails, roll back the inventory change as well.
    with db:
        if fixed:
            update = db.execute(
                "UPDATE inventory SET remaining = remaining - 1 "
                "WHERE id = 1 AND remaining > 0"
            )
            if update.rowcount == 0:
                return False
        elif tickets_seen > 0:
            # The original checkout trusts the stock it read earlier.
            db.execute(
                "UPDATE inventory SET remaining = ? WHERE id = 1",
                (tickets_seen - 1,),
            )
        else:
            return False

        db.execute("INSERT INTO bookings (buyer) VALUES (?)", (buyer,))
    return True


async def run(schedule: Sequence[str], *, fixed: bool) -> BookingRun:
    with closing(sqlite3.connect(":memory:")) as db:
        create_tables(db)

        def read_stock() -> int:
            return db.execute("SELECT remaining FROM inventory WHERE id = 1").fetchone()[0]

        async def checkout(replay: Replay, buyer: str) -> None:
            tickets_seen = await replay.step(buyer, "read_stock", read_stock)

            def book() -> str:
                booked = reserve_ticket(db, buyer, tickets_seen, fixed=fixed)
                return "Confirmed" if booked else "Sold out"

            await replay.step(buyer, "reserve", book)

        trace = await run_replay(schedule, {"A": checkout, "B": checkout})
        bookings = db.execute("SELECT buyer FROM bookings ORDER BY buyer")
        return BookingRun(trace, tuple(buyer for (buyer,) in bookings), read_stock())
