import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replay import ReplayError, load_schedule, run_replay


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_controls_order_when_workflows_start_in_reverse(self):
        order = []

        async def work(replay, actor):
            await replay.step(actor, "read", lambda: order.append(f"{actor}.read"))
            await replay.step(actor, "write", lambda: order.append(f"{actor}.write"))

        schedule = ("A.read", "B.read", "A.write", "B.write")
        trace = await run_replay(schedule, {"B": work, "A": work})
        self.assertEqual(tuple(order), schedule)
        self.assertEqual(tuple(entry.checkpoint for entry in trace), schedule)

    async def test_rejects_duplicate_checkpoint_names(self):
        with self.assertRaisesRegex(ReplayError, "must be unique"):
            await run_replay(("A.read", "A.read"), {})

    async def test_rejects_checkpoint_absent_from_schedule(self):
        async def work(replay, actor):
            await replay.step(actor, "typo", lambda: None)

        with self.assertRaisesRegex(ReplayError, "A.typo is absent"):
            await run_replay(("A.read",), {"A": work})

    async def test_rejects_a_second_execution_of_the_same_checkpoint(self):
        async def work(replay, actor):
            await replay.step(actor, "read", lambda: None)
            await replay.step(actor, "read", lambda: None)

        with self.assertRaisesRegex(ReplayError, "A.read already ran"):
            await run_replay(("A.read",), {"A": work})

    async def test_reports_first_unfinished_checkpoint(self):
        async def work(replay, actor):
            await replay.step(actor, "read", lambda: None)

        with self.assertRaisesRegex(ReplayError, "ended before checkpoint A.write"):
            await run_replay(("A.read", "A.write"), {"A": work})

    async def test_times_out_and_stops_a_workflow_waiting_for_a_turn(self):
        stopped = asyncio.Event()

        async def work(replay, actor):
            try:
                await replay.step(actor, "write", lambda: None)
            finally:
                stopped.set()

        with self.assertRaisesRegex(ReplayError, "timed out waiting for A.read"):
            await run_replay(("A.read", "B.write"), {"B": work}, timeout=0.1)
        self.assertTrue(stopped.is_set())

    async def test_failed_workflow_stops_a_waiting_workflow(self):
        stopped = asyncio.Event()

        async def wait_for_write(replay, actor):
            try:
                await replay.step(actor, "write", lambda: None)
            finally:
                stopped.set()

        async def fail(replay, actor):
            raise RuntimeError("Simulated read failure")

        with self.assertRaisesRegex(RuntimeError, "Simulated read failure"):
            await run_replay(("A.read", "B.write"), {"B": wait_for_write, "A": fail})
        self.assertTrue(stopped.is_set())

    def test_rejects_a_fixture_without_a_list_of_names(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('["A.read", 3]', encoding="utf-8")
            with self.assertRaisesRegex(ReplayError, "JSON list of checkpoint names"):
                load_schedule(path)
