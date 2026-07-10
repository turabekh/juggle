"""Minimal iCalendar (.ics) generation — pure, dependency-free (PRD §7.4)."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class IcalEvent:
    uid: str
    summary: str
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    description: str | None = None


def _fmt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(events: list[IcalEvent], *, now: datetime | None = None) -> str:
    stamp = _fmt(now or datetime.now(UTC))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Juggle//Bookings//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_fmt(event.starts_at)}",
            f"DTEND:{_fmt(event.ends_at)}",
            f"SUMMARY:{_escape(event.summary)}",
        ]
        if event.location:
            lines.append(f"LOCATION:{_escape(event.location)}")
        if event.description:
            lines.append(f"DESCRIPTION:{_escape(event.description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
