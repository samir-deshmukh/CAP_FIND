from __future__ import annotations

from pathlib import Path

from backend import main as main_module


class _Cursor:
    def __init__(self, rows=None, row=None, rowcount=1):
        self._rows = rows or []
        self._row = row
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, jobs, saved):
        self.jobs = jobs
        self.saved = saved
        self.statements = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SELECT J.ID,J.STORED_PATH"):
            rows = self.jobs
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT EXISTS"):
            return _Cursor(row=self.saved)
        return _Cursor()

    def commit(self):
        self.committed = True


def _run_recovery(monkeypatch, tmp_path: Path, saved, jobs=None):
    source = tmp_path / "imports" / "source.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-test")
    connection = _Connection(
        jobs=jobs if jobs is not None else [{"id": 41, "stored_path": "imports/source.pdf"}],
        saved=saved,
    )
    events = []
    monkeypatch.setattr(main_module, "BASE", tmp_path)
    monkeypatch.setattr(main_module, "connect", lambda: connection)
    monkeypatch.setattr(main_module, "event", lambda *args: events.append(args))

    main_module._recover_interrupted_imports()
    return connection, events


def test_expired_job_with_staging_is_preserved_for_review(monkeypatch, tmp_path):
    connection, events = _run_recovery(
        monkeypatch, tmp_path, {"has_staging": True, "has_results": False}
    )

    statements = [sql.upper() for sql, _ in connection.statements]
    assert not any("DELETE FROM IMPORT_STAGING_RECORDS" in sql for sql in statements)
    assert not any("DELETE FROM IMPORT_RESULTS" in sql for sql in statements)
    update = next(sql for sql, _ in connection.statements if "UPDATE import_jobs SET status='REVIEW_REQUIRED'" in sql)
    assert "worker_lease_until=NULL" in update
    assert any(event_args[1] == 41 and event_args[2] == "RECOVERY_REVIEW_REQUIRED" for event_args in events)
    assert connection.committed


def test_expired_job_without_saved_output_can_be_requeued(monkeypatch, tmp_path):
    connection, events = _run_recovery(
        monkeypatch, tmp_path, {"has_staging": False, "has_results": False}
    )

    update = next(sql for sql, _ in connection.statements if "UPDATE import_jobs SET status='QUEUED'" in sql)
    assert "current_page=0" in update
    assert "current_chunk=0" in update
    assert any(event_args[1] == 41 and event_args[2] == "RECOVERED" for event_args in events)
    assert not any("DELETE FROM import_staging_records" in sql for sql, _ in connection.statements)
    assert not any("DELETE FROM import_results" in sql for sql, _ in connection.statements)


def test_expired_local_worker_job_is_marked_retryable(monkeypatch, tmp_path):
    connection, events = _run_recovery(
        monkeypatch,
        tmp_path,
        {"has_staging": False, "has_results": False},
        jobs=[{"id": 42, "stored_path": "local://job_42"}],
    )

    update = next(params for sql, params in connection.statements if "UPDATE import_jobs SET status='FAILED'" in sql)
    assert "Local extraction stopped without returning a CSV" in update[0]
    assert any(event_args[1] == 42 and event_args[2] == "RECOVERY_FAILED" for event_args in events)
    assert connection.committed


def test_expired_server_job_without_source_or_staging_is_failed(monkeypatch, tmp_path):
    connection, events = _run_recovery(
        monkeypatch,
        tmp_path,
        {"has_staging": False, "has_results": False},
        jobs=[{"id": 43, "stored_path": "imports/missing.pdf"}],
    )

    update = next(params for sql, params in connection.statements if "UPDATE import_jobs SET status='FAILED'" in sql)
    assert "source PDF is missing and no staged output exists" in update[0]
    assert any(event_args[1] == 43 and event_args[2] == "RECOVERY_FAILED" for event_args in events)
