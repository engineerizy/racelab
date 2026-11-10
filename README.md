# RaceLab

RaceLab makes timing bugs in Python workflows repeatable. It uses a saved order of operations to run the same scenario against the original code and a fix. The terminal shows what each participant saw, when they wrote to the database, and which rule held or failed.

## Run both demos

Open a terminal in the folder containing `racelab.py`. RaceLab uses Python 3.11 or newer and the standard library, including SQLite.

```powershell
py racelab.py all
py -m unittest discover -s tests -v
```

Use `python3` in place of `py` on macOS or Linux. Run `py racelab.py last-ticket` or `py racelab.py lost-update` to show one demo at a time.

| Replay | Original result | Fixed result |
| --- | --- | --- |
| Last-ticket double booking | Both buyers see one ticket available and both get confirmed. | One buyer gets confirmed. The second gets **Sold out**. |
| Lost support-ticket update | Agent A closes a ticket. Agent B saves an old copy and reopens it by accident. | Agent A’s change is preserved. Agent B sees a conflict and can reload the ticket. |

## How the replay works

1. Each participant runs as an `asyncio` task and wraps synchronous operations such as SQLite reads or writes in named `replay.step(...)` calls.
2. The runner executes a checkpoint when its name is next in the JSON schedule. It records the result before allowing the next checkpoint. Both participants can read the same starting state before either is allowed to write.
3. The original and fixed examples each start with a fresh in-memory SQLite database. The CLI uses the same schedule for both runs and verifies the expected rule violation and recovery.

The [last-ticket fixture](fixtures/last-ticket.json) schedules both stock reads before either reservation. The [support-ticket fixture](fixtures/lost-update.json) schedules both agents to load version zero before either can save. Each scheduled checkpoint runs once. A missing checkpoint produces an error with the step the replay was waiting for.

## How the fixes work

- **Booking.** A conditional SQL update decrements stock only when a ticket is available. The inventory update and booking insert share a transaction, so a failed booking insert also rolls back the stock change.
- **Support ticket.** The save checks the version the agent originally loaded. A successful save increments the version. A stale save updates zero rows and returns an explicit conflict.

## Project files

| File or folder | Purpose |
| --- | --- |
| [`racelab.py`](racelab.py) | Terminal commands and before-and-after timelines |
| [`replay.py`](replay.py) | Reusable checkpoint runner and schedule loading |
| [`examples/`](examples/) | SQLite workflows and their fixes |
| [`fixtures/`](fixtures/) | Saved JSON schedules used in the demos and tests |
| [`tests/`](tests/) | Regression tests for the runner, database state and rollback |

The GitHub Actions workflow runs the tests and demos on Windows and Linux after pushes and pull requests. To try another workflow, give its steps unique checkpoint names, record an order in a fixture, and test the final state you expect.
