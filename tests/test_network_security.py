from starlette.requests import Request

from backend.admin.network import client_ip


def _request(peer, headers=()):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": list(headers),
        "client": (peer, 12345),
        "server": ("testserver", 443),
    })


def test_forwarded_header_is_ignored_from_untrusted_peer(monkeypatch):
    monkeypatch.setenv("CET_TRUSTED_PROXY_IPS", "10.0.0.0/8")
    request = _request("198.51.100.8", [(b"x-forwarded-for", b"203.0.113.99")])
    assert client_ip(request) == "198.51.100.8"


def test_forwarded_header_only_used_from_configured_proxy(monkeypatch):
    monkeypatch.setenv("CET_TRUSTED_PROXY_IPS", "10.0.0.0/8")
    request = _request(
        "10.0.0.7",
        [(b"x-forwarded-for", b"203.0.113.99, 198.51.100.21")],
    )
    assert client_ip(request) == "198.51.100.21"


def test_invalid_forwarded_values_fall_back_to_proxy(monkeypatch):
    monkeypatch.setenv("CET_TRUSTED_PROXY_IPS", "10.0.0.0/8")
    request = _request("10.0.0.7", [(b"x-forwarded-for", b"attacker, invalid")])
    assert client_ip(request) == "10.0.0.7"
