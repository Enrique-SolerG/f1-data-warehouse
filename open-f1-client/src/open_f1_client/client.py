import asyncio
from datetime import datetime, timedelta
from typing import Self
from urllib.parse import quote

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from yarl import URL

from open_f1_client.models import OpenF1Record

BASE_URL = "https://api.openf1.org/v1"
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
# Below this, halving a window can't make a 422 go away.
MIN_WINDOW = timedelta(seconds=1)

type Filter = str | int | float


class OpenF1QueryTooLarge(Exception):
    """OpenF1 rejected the query (422) and it can't be split any further."""


class _TooMuchData(Exception):
    pass


def _query(
    filters: dict[str, Filter], start: datetime | None, end: datetime | None
) -> str:
    """Build the query string by hand: OpenF1 reads comparison operators from
    the raw query (``date>=...``), and aiohttp would percent-encode them."""
    terms = [(key, "=", value) for key, value in filters.items()]
    if start is not None:
        terms.append(("date", ">=", start.isoformat()))
    if end is not None:
        terms.append(("date", "<", end.isoformat()))
    return "&".join(f"{quote(k)}{op}{quote(str(v), safe=':')}" for k, op, v in terms)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status in RETRYABLE_STATUS
    return isinstance(exc, (aiohttp.ClientConnectionError, TimeoutError))


class OpenF1Client:
    """Async OpenF1 client. Use as ``async with OpenF1Client() as client``."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30,
        max_concurrency: int = 3,
        max_attempts: int = 6,
    ) -> None:
        self._base_url = base_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_attempts = max_attempts
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch[T: OpenF1Record](
        self,
        model: type[T],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        **filters: Filter,
    ) -> list[T]:
        """Fetch every ``model`` record matching ``filters``.

        ``start``/``end`` bound the ``date`` field as ``[start, end)``. When
        given, a query OpenF1 rejects as too large is split into halves and
        fetched concurrently until each part is accepted.
        """
        query = _query(filters, start, end)
        try:
            raw = await self._get(model.endpoint, query)
        except _TooMuchData:
            if start is None or end is None or end - start < MIN_WINDOW:
                raise OpenF1QueryTooLarge(
                    f"{model.endpoint}?{query}: pass a narrower start/end window"
                ) from None
            mid = start + (end - start) / 2
            first, second = await asyncio.gather(
                self.fetch(model, start=start, end=mid, **filters),
                self.fetch(model, start=mid, end=end, **filters),
            )
            return first + second
        return model.validate_many(raw) if raw is not None else []

    async def _get(self, endpoint: str, query: str) -> bytes | None:
        """GET one endpoint with retries. Returns None when there are no results."""
        if self._session is None:
            raise RuntimeError("OpenF1Client must be used as an async context manager")
        retrying = AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            wait=wait_exponential_jitter(initial=1, max=60),
            stop=stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        url = URL(f"{self._base_url}/{endpoint}?{query}", encoded=True)
        async for attempt in retrying:
            with attempt:
                async with (
                    self._semaphore,
                    self._session.get(url) as resp,
                ):
                    if resp.status == 404:  # OpenF1's "No results found."
                        return None
                    if resp.status == 422:  # "asking for too much data at once"
                        raise _TooMuchData
                    resp.raise_for_status()
                    return await resp.read()
        raise AssertionError("unreachable: tenacity reraises on the last attempt")
