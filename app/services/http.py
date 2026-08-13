from __future__ import annotations

import time

import httpx


TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def request_with_retry_client(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (0.5, 1.5),
    **kwargs,
) -> httpx.Response:
    """Use an existing client and retry only clearly transient transport failures."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code not in TRANSIENT_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError(
                f"Transient HTTP status {response.status_code}",
                request=response.request,
                response=response,
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_error = exc

        if attempt < attempts - 1:
            delay = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
            time.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed without a captured error")


def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float,
    attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (0.5, 1.5),
    **kwargs,
) -> httpx.Response:
    """Make a small number of retries for clearly transient HTTP failures.

    Validation and parsing errors are intentionally not retried here. A changed upstream
    format should fail closed rather than being hammered repeatedly.
    """
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return request_with_retry_client(
            client,
            method,
            url,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            **kwargs,
        )
