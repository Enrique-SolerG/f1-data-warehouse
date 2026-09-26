"""OpenF1 API client.

Async core (``OpenF1Client``) plus ``fetch``, a sync entry point for Airflow tasks.
"""

import asyncio
from datetime import datetime

from open_f1_client.client import Filter, OpenF1Client, OpenF1QueryTooLarge
from open_f1_client.models import (
    CarDataSample,
    Driver,
    Lap,
    Meeting,
    OpenF1Record,
    Pit,
    Position,
    Session,
    Weather,
)

__all__ = [
    "CarDataSample",
    "Driver",
    "Lap",
    "Meeting",
    "OpenF1Client",
    "OpenF1QueryTooLarge",
    "OpenF1Record",
    "Pit",
    "Position",
    "Session",
    "Weather",
    "fetch",
]


def fetch[T: OpenF1Record](
    model: type[T],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    **filters: Filter,
) -> list[T]:
    """Sync wrapper around ``OpenF1Client.fetch``. Must not be called from a running event loop."""

    async def run() -> list[T]:
        async with OpenF1Client() as client:
            return await client.fetch(model, start=start, end=end, **filters)

    return asyncio.run(run())
