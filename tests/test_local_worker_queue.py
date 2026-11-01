from pathlib import Path

from backend import local_worker


def test_wait_for_server_staging_keeps_waiting_until_terminal(monkeypatch):
    state = {"job_id": 13}
    results = iter([
        {"status": "EXTRACTING", "message": "Validating rows"},
        {"status": "VALIDATING", "message": "Staging rows"},
        {"status": "STAGED"},
    ])
    polls = []
    monkeypatch.setattr(local_worker, "_remote_get", lambda *_: (polls.append(True), next(results))[1])
    monkeypatch.setattr(local_worker, "_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(local_worker.time, "sleep", lambda *_: None)

    assert local_worker._wait_for_server_staging(state) == {"status": "STAGED"}
    assert len(polls) == 3


def test_cleanup_extraction_outputs_keeps_only_retry_artifact(tmp_path):
    outdir = tmp_path / "artifacts"
    chunk_dir = outdir / ".chunk_work"
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "large-intermediate.pdf").write_bytes(b"intermediate")
    artifact = outdir / "cutoffs.csv"
    artifact.write_text("source_pdf,category\nsource.pdf,NEWCAT\n", encoding="utf-8")
    (outdir / "page_audit.json").write_text("{}", encoding="utf-8")

    local_worker._cleanup_extraction_outputs(outdir, artifact)

    assert artifact.is_file()
    assert sorted(path.name for path in outdir.iterdir()) == ["cutoffs.csv"]
