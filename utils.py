from datetime import datetime, timezone

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def now_iso():
    return datetime.now(timezone.utc).strftime(ISO_FMT)


def add_days_iso(days):
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(ISO_FMT)


def parse_iso(value):
    return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)


def format_postmark(value):
    """'Jan 5, 2026 · 3:42 PM' style label, matching the original UI copy."""
    try:
        dt = parse_iso(value)
    except (ValueError, TypeError):
        return value
    return dt.strftime("%b %-d, %Y") + " · " + dt.strftime("%-I:%M %p")


def active_status(job_row):
    """'expired' if closed OR past expires_at, else 'active' — same rule the
    original React scaffold used to badge jobs."""
    if job_row["status"] == "closed":
        return "expired"
    try:
        if parse_iso(job_row["expires_at"]) <= datetime.now(timezone.utc):
            return "expired"
    except (ValueError, TypeError):
        pass
    return "active"
