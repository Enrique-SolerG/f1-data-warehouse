"""Hits the live OpenF1 API, so it only runs when asked for explicitly.

Fetches every model from a fixed historical weekend (Singapore 2023) to catch
OpenF1 drifting away from our models.
"""

from collections.abc import AsyncIterator

import aiohttp
import pytest
from open_f1_client.client import OpenF1Client
from open_f1_client.models import (
    CarDataSample,
    Driver,
    Lap,
    Meeting,
    OpenF1Model,
    Pit,
    Position,
    Session,
    Weather,
)

MEETING_KEY = 1219
RACE_SESSION_KEY = 9165
DRIVER_NUMBER = 1


@pytest.fixture
async def client() -> AsyncIterator[OpenF1Client]:
    async with aiohttp.ClientSession() as session:
        yield OpenF1Client(session)


@pytest.mark.parametrize(
    ("model", "params"),
    [
        (Meeting, {"meeting_key": MEETING_KEY}),
        (Session, {"session_key": RACE_SESSION_KEY}),
        (Driver, {"session_key": RACE_SESSION_KEY}),
        (Weather, {"session_key": RACE_SESSION_KEY}),
        (Pit, {"session_key": RACE_SESSION_KEY}),
        (Lap, {"session_key": RACE_SESSION_KEY, "driver_number": DRIVER_NUMBER}),
        (
            Position,
            {"session_key": RACE_SESSION_KEY, "driver_number": DRIVER_NUMBER},
        ),
        (
            CarDataSample,
            {"session_key": RACE_SESSION_KEY, "driver_number": DRIVER_NUMBER},
        ),
    ],
    ids=lambda v: v.__name__ if isinstance(v, type) else str(v),
)
async def test_fetch_parses_live_data(
    client: OpenF1Client, model: type[OpenF1Model], params: dict[str, int]
) -> None:
    assert await client.fetch(model, params)
