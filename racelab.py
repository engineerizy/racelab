"""Reproduce and inspect timing-dependent bugs in Python workflows."""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from examples import last_ticket, lost_update
from replay import ReplayError, load_schedule


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCENARIOS = {
    "last-ticket": ("Last-ticket double booking", last_ticket.run),
    "lost-update": ("Lost support-ticket update", lost_update.run),
}


def print_result(heading: str, result: last_ticket.BookingRun | lost_update.TicketRun) -> None:
    print(heading)
    for index, entry in enumerate(result.trace, start=1):
        print(f"  {index}. {entry.checkpoint:<24} {entry.outcome}")
    verdict = "holds" if result.invariant_holds else "violated"
    print(f"  Invariant {verdict}. {result.summary}")


async def show_scenarios(names: Sequence[str]) -> int:
    for name in names:
        title, run = SCENARIOS[name]
        schedule = load_schedule(FIXTURES / f"{name}.json")
        print(f"\n=== {title} ===")

        before = await run(schedule, fixed=False)
        print_result("Before the fix", before)
        after = await run(schedule, fixed=True)
        print_result("After the fix", after)

        if before.invariant_holds or not after.invariant_holds:
            print("The replay did not produce the expected outcomes.", file=sys.stderr)
            return 1
        print("Replay verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        choices=(*SCENARIOS, "all"),
        nargs="?",
        default="last-ticket",
        help="scenario to replay (default: last-ticket)",
    )
    selected = parser.parse_args().scenario
    names = tuple(SCENARIOS) if selected == "all" else (selected,)
    try:
        return asyncio.run(show_scenarios(names))
    except (ReplayError, OSError, ValueError) as error:
        print(f"RaceLab could not run the replay. {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
