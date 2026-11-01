import backend.main as main


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, shared):
        self.shared = shared

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.shared["queries"].append((normalized, params))
        if "SELECT COUNT(*) AS missing_count" in normalized:
            return FakeResult({"missing_count": 4})
        return FakeResult()

    def commit(self):
        pass


def test_derived_data_build_completes_when_metadata_check_returns_mapping_row(monkeypatch):
    shared = {"queries": []}
    monkeypatch.setattr(main, "connect", lambda: FakeConnection(shared))
    monkeypatch.setattr(main.subprocess, "run", lambda *args, **kwargs: None)

    main._run_derived_data_build(123, None)

    updates = [q for q, _ in shared["queries"] if "UPDATE derived_data_build_jobs SET status=" in q]
    assert any("status='COMPLETED'" in q for q in updates)
    assert not any("status='FAILED'" in q for q in updates)
    completion = [params for q, params in shared["queries"] if "status='COMPLETED'" in q]
    assert completion and "4 latest institution/choice-code records" in completion[0][0]
