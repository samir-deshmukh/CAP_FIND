from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from backend import main


def _request():
    return Request({
        'type': 'http', 'http_version': '1.1', 'method': 'POST',
        'scheme': 'https', 'path': '/admin/api/remote-worker/imports',
        'raw_path': b'/admin/api/remote-worker/imports', 'query_string': b'',
        'headers': [], 'client': ('testclient', 123), 'server': ('testserver', 443),
    })


def test_remote_upload_fails_closed_without_private_durable_storage(monkeypatch):
    monkeypatch.setenv('CAPFIND_REMOTE_WORKER_TOKEN', 'x' * 40)
    monkeypatch.setattr(main, 'require', lambda *args, **kwargs: {'uid': 1})
    monkeypatch.setattr(main, 'storage_backend', lambda: 'local')
    upload = UploadFile(filename='generic.pdf', file=BytesIO(b'%PDF-valid'))

    with pytest.raises(HTTPException) as error:
        main.create_remote_worker_import(_request(), upload)

    assert error.value.status_code == 503
    assert 'private durable' in error.value.detail


@pytest.mark.parametrize(
    ('configured', 'authorization', 'expected_status'),
    [('', 'Bearer arbitrary', 503), ('x' * 40, 'Bearer wrong', 401)],
)
def test_remote_worker_claim_requires_shared_secret(monkeypatch, configured, authorization, expected_status):
    monkeypatch.setenv('CAPFIND_REMOTE_WORKER_TOKEN', configured)
    request = _request()
    request.scope['headers'] = [(b'authorization', authorization.encode())]

    with pytest.raises(HTTPException) as error:
        main._remote_worker_auth(request)

    assert error.value.status_code == expected_status


def test_server_artifact_paths_use_job_ids_not_uploaded_filenames(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BASE', tmp_path)
    artifact_dir = tmp_path / 'data' / 'local_import_artifacts' / 'job_42'
    artifact_dir.mkdir(parents=True)
    canonical = artifact_dir / 'job_42_cutoffs.csv'

    assert main._local_import_artifact_path(42, 'CUTOFFS') == canonical
    canonical.write_text('source_pdf,page\n')
    assert main._local_import_artifact_path(42, 'CUTOFFS') == canonical


def test_startup_cleanup_removes_only_root_upload_scratch_files(tmp_path, monkeypatch):
    imports = tmp_path / 'imports'
    imports.mkdir()
    (imports / 'failed.upload').write_bytes(b'leftover')
    (imports / 'retained.pdf').write_bytes(b'%PDF-source')
    nested = imports / 'job_42'
    nested.mkdir()
    (nested / 'artifact.upload').write_bytes(b'not an upload request temp')
    monkeypatch.setattr(main, 'IMPORTS', imports)

    assert main._cleanup_abandoned_upload_temps() == 1
    assert not (imports / 'failed.upload').exists()
    assert (imports / 'retained.pdf').exists()
    assert (nested / 'artifact.upload').exists()

def test_control_marker_cleanup_stays_under_fixed_job_root(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BASE', tmp_path)
    job_dir = tmp_path / 'data' / 'import_staging' / 'job_42'
    job_dir.mkdir(parents=True)
    (job_dir / 'CANCEL').touch()
    (job_dir / 'PAUSE').touch()

    main._clear_import_control_markers(42)

    assert not (job_dir / 'CANCEL').exists()
    assert not (job_dir / 'PAUSE').exists()
