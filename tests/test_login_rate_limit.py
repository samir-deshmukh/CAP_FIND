import backend.main as main


def test_login_limiter_throttles_and_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(main, "_LOGIN_RATE", {})

    assert all(main._login_ok("198.51.100.4") for _ in range(5))
    assert not main._login_ok("198.51.100.4")
    clock[0] += 61
    assert main._login_ok("198.51.100.4")


def test_login_limiter_bounds_high_cardinality_keys(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(main, "_LOGIN_RATE", {"first": [100.0], "second": [100.0]})
    monkeypatch.setattr(main, "_LOGIN_MAX_KEYS", 2)

    assert main._login_ok("third")
    assert len(main._LOGIN_RATE) <= 2
    assert "third" in main._LOGIN_RATE
