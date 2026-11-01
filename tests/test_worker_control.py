import json
import threading
import time

import pytest

from scripts import worker_control


def test_checkpoint_is_noop_without_local_worker_environment(monkeypatch):
    monkeypatch.delenv("CAPFIND_JOB_CONTROL_DIR", raising=False)
    worker_control.checkpoint(1, 10)


def test_checkpoint_writes_atomic_progress(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPFIND_JOB_CONTROL_DIR", str(tmp_path))
    worker_control.checkpoint(3, 12)
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["page"] == 3
    assert progress["total"] == 12
    assert progress["state"] == "RUNNING"
    assert not (tmp_path / "progress.json.tmp").exists()


def test_checkpoint_waits_until_pause_marker_removed(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPFIND_JOB_CONTROL_DIR", str(tmp_path))
    (tmp_path / "PAUSE").touch()
    finished = threading.Event()

    def run():
        worker_control.checkpoint(4, 10)
        finished.set()

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        try:
            progress = json.loads((tmp_path / "progress.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.02)
            continue
        if progress["state"] == "PAUSED":
            break
        time.sleep(0.02)
    else:
        pytest.fail("worker did not publish PAUSED progress")
    assert not finished.is_set()
    (tmp_path / "PAUSE").unlink()
    thread.join(timeout=2)
    assert finished.is_set()
    assert json.loads((tmp_path / "progress.json").read_text())["state"] == "RUNNING"


def test_checkpoint_cancels_while_paused(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPFIND_JOB_CONTROL_DIR", str(tmp_path))
    (tmp_path / "PAUSE").touch()
    (tmp_path / "CANCEL").touch()
    with pytest.raises(RuntimeError, match="CAPFIND_WORKER_CANCELLED"):
        worker_control.checkpoint(2, 8)
