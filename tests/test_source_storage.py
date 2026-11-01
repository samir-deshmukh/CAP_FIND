
import pytest
from io import BytesIO

from backend.admin import source_storage as storage


def test_storage_backend_defaults_to_local_without_payment_setup(monkeypatch):
    monkeypatch.delenv("CET_PDF_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("CET_ENV", "production")
    assert storage.storage_backend() == "local"
    monkeypatch.setenv("CET_PDF_STORAGE_BACKEND", "s3")
    assert storage.storage_backend() == "s3"


def test_local_storage_round_trip_is_confined_to_import_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "BASE", tmp_path)
    monkeypatch.setattr(storage, "LOCAL_IMPORTS", tmp_path / "data" / "imports")
    monkeypatch.setenv("CET_PDF_STORAGE_BACKEND", "local")
    source = tmp_path / "upload.tmp"
    source.write_bytes(b"%PDF-test")
    stored = storage.store_source_pdf(source, "imports/test.pdf", "abc123")
    assert stored == "data/imports/test.pdf"
    assert not source.exists()
    with storage.materialize_source(stored) as materialized:
        assert materialized.read_bytes() == b"%PDF-test"
    storage.delete_source(stored)
    assert not (tmp_path / stored).exists()


def test_object_uri_is_parsed_and_invalid_uri_is_rejected():
    assert storage._parse_object_uri("s3://private-bucket/imports/a%20b.pdf") == (
        "private-bucket", "imports/a b.pdf"
    )
    with pytest.raises(ValueError):
        storage._parse_object_uri("https://example.com/public.pdf")


def test_production_storage_fails_closed_without_credentials(monkeypatch):
    monkeypatch.setenv("CET_PDF_STORAGE_BACKEND", "s3")
    for key in ("CET_S3_ENDPOINT_URL", "CET_S3_BUCKET",
                "CET_S3_ACCESS_KEY_ID", "CET_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(storage.StorageNotConfigured):
        storage._s3_config()


def test_s3_upload_uses_single_streaming_put_object(tmp_path, monkeypatch):
    class FakeClient:
        def put_object(self, **kwargs):
            assert kwargs['Bucket'] == 'private'
            assert kwargs['Key'] == 'imports/file.pdf'
            assert kwargs['ContentLength'] == 9
            assert kwargs['Body'].read() == b'%PDF-test'
            assert kwargs['Metadata'] == {'sha256': 'abc123'}

    source = tmp_path / 'source.pdf'
    source.write_bytes(b'%PDF-test')
    monkeypatch.setenv('CET_PDF_STORAGE_BACKEND', 's3')
    monkeypatch.setattr(storage, 'storage_backend', lambda: 's3')
    # Avoid a remote quota listing while asserting the bounded upload call.
    class QuotaClient(FakeClient):
        def list_objects_v2(self, **kwargs):
            return {'IsTruncated': False, 'Contents': []}

    monkeypatch.setattr(storage, '_client', lambda: (QuotaClient(), 'private'))
    assert storage.store_source_pdf(source, 'imports/file.pdf', 'abc123') == 's3://private/imports/file.pdf'


def test_s3_download_streams_to_temporary_file(tmp_path, monkeypatch):
    class FakeBody(BytesIO):
        closed_by_client = False

        def close(self):
            self.closed_by_client = True
            super().close()

    body = FakeBody(b'%PDF-test')

    class FakeClient:
        def get_object(self, **kwargs):
            assert kwargs == {'Bucket': 'private', 'Key': 'imports/file.pdf'}
            return {'Body': body}

    monkeypatch.setattr(storage, '_client', lambda: (FakeClient(), 'private'))
    monkeypatch.setattr(storage, '_parse_object_uri', lambda value: ('private', 'imports/file.pdf'))
    with storage.materialize_source('s3://private/imports/file.pdf') as materialized:
        assert materialized.read_bytes() == b'%PDF-test'
    assert body.closed_by_client
