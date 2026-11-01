import asyncio

import pytest

from backend import local_worker


def _preflight(origin):
    async def run():
        sent = []
        request_headers = [
            (b"origin", origin.encode()),
            (b"access-control-request-method", b"POST"),
            (b"access-control-request-headers", b"content-type"),
            (b"access-control-request-private-network", b"true"),
        ]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "OPTIONS",
            "scheme": "https",
            "path": "/jobs",
            "raw_path": b"/jobs",
            "query_string": b"",
            "headers": request_headers,
            "server": ("testserver", 443),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await local_worker.app(scope, receive, send)
        response = sent[0]
        return response["status"], dict(response["headers"])

    return asyncio.run(run())


@pytest.mark.parametrize(
    "backend_url",
    [
        "https://cetfind.onrender.com",
        "https://cetfind-backend.onrender.com",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
)
def test_backend_url_allows_only_expected_hosts(backend_url):
    assert local_worker._backend_ok(backend_url) == backend_url


@pytest.mark.parametrize(
    "backend_url",
    [
        "https://example.com",
        "http://192.168.1.5:8000",
        "file:///etc/passwd",
        "https://cetfind-backend.onrender.com.attacker.example",
    ],
)
def test_backend_url_rejects_untrusted_hosts(backend_url):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        local_worker._backend_ok(backend_url)


def test_production_admin_origins_are_allowlisted():
    assert "https://cetfind.onrender.com" in local_worker.ALLOWED_ORIGINS
    assert "https://cetfind-backend.onrender.com" in local_worker.ALLOWED_ORIGINS


def test_private_network_preflight_allows_hosted_admin_to_reach_loopback_worker():
    status, headers = _preflight("https://cetfind.onrender.com")

    assert status == 200
    assert headers[b"access-control-allow-origin"] == b"https://cetfind.onrender.com"
    assert headers[b"access-control-allow-private-network"] == b"true"


def test_private_network_preflight_still_rejects_untrusted_origins():
    status, headers = _preflight("https://attacker.example")

    assert status == 400
    assert b"access-control-allow-origin" not in headers


def test_worker_binds_only_to_loopback_by_default():
    assert local_worker.ALLOWED_HOSTS <= {
        "cetfind.onrender.com",
        "cetfind-backend.onrender.com",
        "localhost",
        "127.0.0.1",
    }


def test_remote_claim_is_disabled_without_shared_worker_secret(monkeypatch):
    monkeypatch.delenv("CAPFIND_REMOTE_WORKER_TOKEN", raising=False)
    assert local_worker._claim_remote_job() is False
