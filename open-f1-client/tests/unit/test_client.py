from collections.abc import AsyncIterator, Iterator

import aiohttp
import pytest
from aioresponses import aioresponses
from open_f1_client.client import BASE_URL, OpenF1Client, RetryPolicy
from open_f1_client.models import Driver
from pydantic import ValidationError
from yarl import URL

DRIVERS_URL = f"{BASE_URL}/drivers?session_key=9158"

DRIVER_JSON = {
    "session_key": 9158,
    "meeting_key": 1219,
    "driver_number": 1,
    "first_name": "Max",
    "last_name": "Verstappen",
    "broadcast_name": "M VERSTAPPEN",
    "name_acronym": "VER",
    "team_name": "Red Bull Racing",
    "team_colour": "3671C6",
    "country_code": "NED",
    "headshot_url": None,
}


@pytest.fixture
def api() -> Iterator[aioresponses]:
    with aioresponses() as m:
        yield m


@pytest.fixture
async def client() -> AsyncIterator[OpenF1Client]:
    async with aiohttp.ClientSession() as session:
        # No backoff, so retry tests don't sleep.
        yield OpenF1Client(session, retry_policy=RetryPolicy(backoff_multiplier=0))


def request_count(api: aioresponses) -> int:
    return len(api.requests.get(("GET", URL(DRIVERS_URL)), []))


async def test_fetch_returns_models_from_the_model_endpoint(
    api: aioresponses, client: OpenF1Client
) -> None:
    api.get(DRIVERS_URL, payload=[DRIVER_JSON])

    drivers = await client.fetch(Driver, {"session_key": 9158})

    assert drivers == [Driver(**DRIVER_JSON)]
    assert request_count(api) == 1


async def test_fetch_rejects_payload_not_matching_the_model(
    api: aioresponses, client: OpenF1Client
) -> None:
    api.get(DRIVERS_URL, payload=[{"driver_number": 1}])

    with pytest.raises(ValidationError):
        await client.fetch(Driver, {"session_key": 9158})


@pytest.mark.parametrize(
    "failure",
    [{"status": 503}, {"exception": aiohttp.ClientConnectionError()}],
    ids=["503", "connection-error"],
)
async def test_fetch_retries_transient_failure(
    api: aioresponses, client: OpenF1Client, failure: dict
) -> None:
    api.get(DRIVERS_URL, **failure)
    api.get(DRIVERS_URL, payload=[DRIVER_JSON])

    drivers = await client.fetch(Driver, {"session_key": 9158})

    assert drivers == [Driver(**DRIVER_JSON)]
    assert request_count(api) == 2


@pytest.mark.parametrize("status", [422, 404])
async def test_fetch_does_not_retry_permanent_failure(
    api: aioresponses, client: OpenF1Client, status: int
) -> None:
    api.get(DRIVERS_URL, status=status)

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await client.fetch(Driver, {"session_key": 9158})

    assert exc_info.value.status == status
    assert request_count(api) == 1
