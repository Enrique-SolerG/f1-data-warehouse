import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp
from pydantic import TypeAdapter
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from open_f1_client.models import OpenF1Model

BASE_URL = "https://api.openf1.org/v1"

# Failures where no response ever arrived. The request may not even have left
# the machine, and these are read-only GETs, so repeating one is always safe.
_TRANSIENT_ERRORS = (
    TimeoutError,
    aiohttp.ServerTimeoutError,
    aiohttp.ClientConnectionError,
)

# Listed explicitly rather than as ">= 500" since "501 Not Implemented" is not retryable.
DEFAULT_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """Everything that governs how hard a request tries, in one place.

    Frozen because otherwise a change mid-run alters the terms of a retry
    already in flight.
    """

    max_attempts: int = 4
    timeout_seconds: float = 10.0
    backoff_multiplier: float = 0.5
    backoff_max_seconds: float = 4.0
    retry_statuses: frozenset[int] = DEFAULT_RETRY_STATUSES

    def tenacity_kwargs(self) -> dict[str, Any]:
        """Translate the policy into tenacity's vocabulary."""
        return {
            "retry": retry_if_exception(self.is_retryable),
            "stop": stop_after_attempt(self.max_attempts),
            "wait": wait_exponential(
                multiplier=self.backoff_multiplier, max=self.backoff_max_seconds
            ),
            "reraise": True,
        }

    def is_retryable(self, exc: BaseException) -> bool:
        """Whether a failed request is worth repeating.

        A failure that carries a status is judged on that status alone: the server
        answered, and its answer says whether asking again could ever help. OpenF1's
        422 ("too much data at once") is the case that matters here - it will fail
        identically on every attempt, so retrying it just delays the real error.

        No status at all means the connection broke rather than the request being
        refused, which is the most retryable case there is.
        """
        if isinstance(exc, aiohttp.ClientResponseError):
            return exc.status in self.retry_statuses
        return isinstance(exc, _TRANSIENT_ERRORS)


# This default global variable exists to make it exportable and because
# Ruff raises a warning (B008) since it can't tell it is unmutable (i.e. frozen).
DEFAULT_RETRY_POLICY = RetryPolicy()


class OpenF1Client:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        base_url: str = BASE_URL,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        max_concurrent_requests: int = 10,
    ):
        self._session = session
        self._base_url = base_url
        self._max_concurrent_requests = max_concurrent_requests
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._retry_policy = retry_policy
        self._timeout = aiohttp.ClientTimeout(total=retry_policy.timeout_seconds)

    async def fetch[M: OpenF1Model](
        self, model: type[M], params: Mapping[str, str | int] | None = None
    ) -> list[M]:
        text = await self._get(model.endpoint, params or {})
        return TypeAdapter(list[model]).validate_json(text)

    async def _get(self, endpoint: str, params: Mapping[str, str | int]) -> str:
        return await AsyncRetrying(**self._retry_policy.tenacity_kwargs())(
            self._get_once, endpoint, params
        )

    async def _get_once(self, endpoint: str, params: Mapping[str, str | int]) -> str:
        async with (
            self._semaphore,
            self._session.get(
                f"{self._base_url}/{endpoint}", params=params, timeout=self._timeout
            ) as response,
        ):
            response.raise_for_status()
            return await response.text()
