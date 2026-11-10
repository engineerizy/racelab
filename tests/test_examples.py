import sqlite3
import unittest
from contextlib import closing

from examples import last_ticket, lost_update
from racelab import FIXTURES
from replay import load_schedule


class LastTicketTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.schedule = load_schedule(FIXTURES / "last-ticket.json")

    async def test_original_checkout_confirms_two_bookings_for_one_ticket(self):
        original = await last_ticket.run(self.schedule, fixed=False)
        self.assertEqual(original.buyers, ("A", "B"))
        self.assertEqual(original.remaining, 0)
        self.assertFalse(original.invariant_holds)
        self.assertEqual(
            [entry.outcome for entry in original.trace], ["1", "1", "Confirmed", "Confirmed"]
        )

    async def test_conditional_reservation_confirms_only_one_booking(self):
        corrected = await last_ticket.run(self.schedule, fixed=True)
        self.assertEqual(corrected.buyers, ("A",))
        self.assertEqual(corrected.remaining, 0)
        self.assertTrue(corrected.invariant_holds)
        self.assertEqual(corrected.trace[-1].outcome, "Sold out")

    async def test_first_writer_wins_when_buyers_save_in_reverse_order(self):
        schedule = (*self.schedule[:2], "B.reserve", "A.reserve")
        corrected = await last_ticket.run(schedule, fixed=True)
        self.assertEqual(corrected.buyers, ("B",))
        self.assertEqual(corrected.remaining, 0)
        self.assertTrue(corrected.invariant_holds)

    def test_failed_booking_write_rolls_back_the_stock_change(self):
        with closing(sqlite3.connect(":memory:")) as db:
            last_ticket.create_tables(db)
            db.executescript(
                """
                CREATE TRIGGER fail_booking_write
                BEFORE INSERT ON bookings
                BEGIN
                    SELECT RAISE(ABORT, 'Simulated booking write failure');
                END;
                """
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "Simulated booking"):
                last_ticket.reserve_ticket(db, "A", 1, fixed=True)
            self.assertEqual(db.execute("SELECT remaining FROM inventory").fetchone(), (1,))
            self.assertEqual(db.execute("SELECT buyer FROM bookings").fetchall(), [])


class LostUpdateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.schedule = load_schedule(FIXTURES / "lost-update.json")

    async def test_original_save_reopens_the_closed_ticket(self):
        original = await lost_update.run(self.schedule, fixed=False)
        self.assertEqual(original.ticket, lost_update.Ticket("Open", "Agent B", 2))
        self.assertEqual(original.trace[-1].outcome, "Saved")
        self.assertFalse(original.invariant_holds)

    async def test_version_guard_keeps_first_save_and_reports_conflict(self):
        corrected = await lost_update.run(self.schedule, fixed=True)
        self.assertEqual(corrected.ticket, lost_update.Ticket("Closed", "nobody", 1))
        self.assertEqual(corrected.trace[-1].outcome, "Conflict. Reload the ticket.")
        self.assertTrue(corrected.invariant_holds)
