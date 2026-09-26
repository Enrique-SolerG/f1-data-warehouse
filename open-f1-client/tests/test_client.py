import asyncio
import re
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from urllib.parse import unquote

import aiohttp
import open_f1_client
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from open_f1_client import OpenF1Client, OpenF1QueryTooLarge, Position
from open_f1_client import client as client_module
from tenacity import wait_none

T0 = datetime(2024, 3, 2, 15, tzinfo=UTC)

type Handler = Callable[[str], Awaitable[web.Response]]


def position(date: datetime, pos: int = 1) -> dict[str, Any]:
    return {
        "date": date.isoformat(),
        "session_key": 1,
        "meeting_key": 2,
        "driver_number": 44,
        "position": pos,
    }


@dataclass
class FakeOpenF1:
    """Serves /position from a queue of handlers (the last one repeats)."""

    handlers: list[Handler] = field(default_factory=list[Handler])
    queries: list[str] = field(default_factory=list[str])  # raw, as sent
    base_url: str = ""

    def respond(self, *handlers: Handler) -> None:
        self.handlers.extend(handlers)

    async def handle(self, request: web.Request) -> web.Response:
        query = request.rel_url.raw_query_string
        self.queries.append(query)
        handler = self.handlers.pop(0) if len(self.handlers) > 1 else self.handlers[0]
        return await handler(query)


def json(data: Any, status: int = 200) -> Handler:
    async def handler(_: str) -> web.Response:
        return web.json_response(data, status=status)

    return handler


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        client_module, "wait_exponential_jitter", lambda **_: wait_none()
    )


@pytest.fixture
async def api() -> AsyncIterator[FakeOpenF1]:
    fake = FakeOpenF1()
    app = web.Application()
    app.router.add_get("/v1/position", fake.handle)
    async with TestServer(app) as server:
        fake.base_url = str(server.make_url("/v1"))
        yield fake


async def test_fetch_sends_filters_and_date_window(api: FakeOpenF1) -> None:
    api.respond(json([position(T0)]))
    end = T0 + timedelta(minutes=1)

    async with OpenF1Client(base_url=api.base_url) as client:
        records = await client.fetch(Position, start=T0, end=end, session_key=1)

    assert [(r.date, r.driver_number) for r in records] == [(T0, 44)]
    # Operators stay literal (OpenF1 rejects "date%3E%3D="); values are encoded.
    assert api.queries == [
        (
            "session_key=1"
            "&date>=2024-03-02T15:00:00%2B00:00"
            "&date<2024-03-02T15:01:00%2B00:00"
        )
    ]


async def test_404_means_no_results(api: FakeOpenF1) -> None:
    api.respond(json({"detail": "No results found."}, status=404))

    async with OpenF1Client(base_url=api.base_url) as client:
        assert await client.fetch(Position, session_key=1) == []


async def test_retries_transient_status_then_succeeds(api: FakeOpenF1) -> None:
    api.respond(json({}, status=503), json({}, status=429), json([position(T0)]))

    async with OpenF1Client(base_url=api.base_url) as client:
        assert len(await client.fetch(Position)) == 1

    assert len(api.queries) == 3


async def test_gives_up_after_max_attempts(api: FakeOpenF1) -> None:
    api.respond(json({}, status=500))

    async with OpenF1Client(base_url=api.base_url, max_attempts=3) as client:
        with pytest.raises(aiohttp.ClientResponseError) as exc:
            await client.fetch(Position)

    assert exc.value.status == 500
    assert len(api.queries) == 3


async def test_does_not_retry_client_errors(api: FakeOpenF1) -> None:
    api.respond(json({}, status=400), json([]))

    async with OpenF1Client(base_url=api.base_url) as client:
        with pytest.raises(aiohttp.ClientResponseError) as exc:
            await client.fetch(Position)

    assert exc.value.status == 400
    assert len(api.queries) == 1


async def test_retries_timeouts(api: FakeOpenF1) -> None:
    async def too_slow(_: str) -> web.Response:
        await asyncio.sleep(1)
        return web.json_response([])

    api.respond(too_slow, json([position(T0)]))

    async with OpenF1Client(base_url=api.base_url, timeout=0.2) as client:
        assert len(await client.fetch(Position)) == 1

    assert len(api.queries) == 2


def test_classifies_transient_errors() -> None:
    def status(code: int) -> aiohttp.ClientResponseError:
        return aiohttp.ClientResponseError(None, (), status=code)  # type: ignore[arg-type]

    assert client_module._is_transient(aiohttp.ClientConnectionError())
    assert client_module._is_transient(TimeoutError())
    assert client_module._is_transient(status(502))
    assert not client_module._is_transient(status(400))
    assert not client_module._is_transient(ValueError())


async def test_422_splits_window_and_keeps_order(api: FakeOpenF1) -> None:
    end = T0 + timedelta(minutes=2)
    mid = T0 + timedelta(minutes=1)

    async def too_much_unless_split(query: str) -> web.Response:
        window = re.fullmatch(r"date>=([^&]+)&date<([^&]+)", query)
        assert window is not None
        start, stop = (datetime.fromisoformat(unquote(g)) for g in window.groups())
        if (start, stop) == (T0, end):
            return web.json_response({"detail": "too much data"}, status=422)
        return web.json_response([position(start, 1), position(start, 2)])

    api.respond(too_much_unless_split)

    async with OpenF1Client(base_url=api.base_url) as client:
        records = await client.fetch(Position, start=T0, end=end)

    assert [(r.date, r.position) for r in records] == [
        (T0, 1),
        (T0, 2),
        (mid, 1),
        (mid, 2),
    ]


async def test_422_without_window_raises(api: FakeOpenF1) -> None:
    api.respond(json({}, status=422))

    async with OpenF1Client(base_url=api.base_url) as client:
        with pytest.raises(OpenF1QueryTooLarge):
            await client.fetch(Position, session_key=1)


async def test_422_stops_splitting_below_min_window(api: FakeOpenF1) -> None:
    api.respond(json({}, status=422))

    async with OpenF1Client(base_url=api.base_url) as client:
        with pytest.raises(OpenF1QueryTooLarge):
            await client.fetch(Position, start=T0, end=T0 + timedelta(seconds=4))


@pytest.fixture
def threaded_api() -> Iterator[str]:
    """A fake OpenF1 on its own loop and thread, so sync ``fetch`` can own the main one."""
    loop = asyncio.new_event_loop()
    app = web.Application()
    fake = FakeOpenF1()
    fake.respond(json([position(T0)]))
    app.router.add_get("/v1/position", fake.handle)
    server = TestServer(app, loop=loop)
    loop.run_until_complete(server.start_server())
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield str(server.make_url("/v1"))
    asyncio.run_coroutine_threadsafe(server.close(), loop).result()
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    loop.close()


def test_sync_fetch(threaded_api: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        open_f1_client, "OpenF1Client", partial(OpenF1Client, base_url=threaded_api)
    )

    records = open_f1_client.fetch(Position, session_key=1)

    assert records[0].driver_number == 44
