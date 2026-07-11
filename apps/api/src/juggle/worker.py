"""Background maintenance worker.

Runs the scheduler's idempotent job tick (waitlist offer/expiry sweep, expired
seat-hold reclaim, pre-session reminders). Drive it from cron with a single tick,
or run it as a long-lived loop in dev:

    uv run python -m juggle.worker            # one tick, then exit (cron-friendly)
    uv run python -m juggle.worker --loop     # every 5 min until interrupted
    uv run python -m juggle.worker --loop --interval 60

Each tick runs in its own transaction and commits; a failure rolls that tick
back and (in loop mode) the worker keeps going.
"""

import argparse
import time
from datetime import UTC, datetime

from juggle.db import SessionLocal
from juggle.modules.scheduler.core import service
from juggle.modules.scheduler.core.schemas import JobSummary


def run_tick() -> JobSummary:
    session = SessionLocal()
    try:
        summary = service.run_due_jobs(session, now=datetime.now(UTC))
        session.commit()
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _log(summary: JobSummary) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    print(
        f"[{ts}] tick: holds_reclaimed={summary.holds_reclaimed} "
        f"waitlist(processed={summary.waitlist_sessions_processed} "
        f"offered={summary.waitlist_offers_made} expired={summary.waitlist_offers_expired}) "
        f"reminders_sent={summary.reminders_sent}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Juggle maintenance worker")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument(
        "--interval", type=int, default=300, help="seconds between ticks in --loop mode"
    )
    args = parser.parse_args()

    if not args.loop:
        _log(run_tick())
        return

    print(f"worker: looping every {args.interval}s (Ctrl-C to stop)", flush=True)
    try:
        while True:
            try:
                _log(run_tick())
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                print(f"tick failed: {exc!r}", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("worker: stopped", flush=True)


if __name__ == "__main__":
    main()
