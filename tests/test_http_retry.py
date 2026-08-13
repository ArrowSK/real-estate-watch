import httpx

from app.services.http import request_with_retry


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


def test_transient_timeout_is_retried(monkeypatch):
    calls = {"count": 0}

    def fake_request(self, method, url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.TimeoutException("temporary timeout")
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    monkeypatch.setattr("app.services.http.time.sleep", lambda _: None)

    response = request_with_retry("GET", "https://example.invalid", timeout=1, attempts=2)
    assert response.status_code == 200
    assert calls["count"] == 2
