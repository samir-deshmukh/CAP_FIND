"""Source-PDF storage adapter.

A private S3-compatible bucket is optional for durable source retention. Explicit
local mode supports no-card hosting but its filesystem may be ephemeral. Keep
original PDFs outside the server until processing and review finish. Objects are
private; this module never creates public URLs.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

BASE = Path(__file__).resolve().parents[2]
LOCAL_IMPORTS = BASE / "data" / "imports"


class StorageNotConfigured(RuntimeError):
    pass


def storage_backend() -> str:
    configured = os.getenv("CET_PDF_STORAGE_BACKEND", "").strip().lower()
    if configured:
        if configured not in {"local", "s3"}:
            raise StorageNotConfigured("CET_PDF_STORAGE_BACKEND must be 'local' or 's3'")
        return configured
    # No-card default: direct uploads use the host filesystem. On Render's
    # free tier this is ephemeral, which the admin UI explicitly warns about.
    # Configure s3 only when a private durable bucket is intentionally set up.
    return "local"


def _s3_config() -> dict:
    endpoint = os.getenv("CET_S3_ENDPOINT_URL", "").strip()
    bucket = os.getenv("CET_S3_BUCKET", "").strip()
    access = os.getenv("CET_S3_ACCESS_KEY_ID", "").strip()
    secret = os.getenv("CET_S3_SECRET_ACCESS_KEY", "").strip()
    if not all((endpoint, bucket, access, secret)):
        raise StorageNotConfigured(
            "Durable PDF storage is not configured. Set CET_S3_ENDPOINT_URL, "
            "CET_S3_BUCKET, CET_S3_ACCESS_KEY_ID and CET_S3_SECRET_ACCESS_KEY."
        )
    return {
        "endpoint_url": endpoint,
        "bucket": bucket,
        "access_key": access,
        "secret_key": secret,
        "region": os.getenv("CET_S3_REGION", "auto").strip() or "auto",
    }


def _client():
    import boto3
    from botocore.config import Config
    cfg = _s3_config()
    client = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        region_name=cfg["region"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
    )
    return client, cfg["bucket"]


def _parse_object_uri(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Invalid source object URI")
    return parsed.netloc, unquote(parsed.path.lstrip("/"))


def store_source_pdf(local_path: Path, object_key: str, sha256: str) -> str:
    local_path = Path(local_path)
    if storage_backend() == "local":
        LOCAL_IMPORTS.mkdir(parents=True, exist_ok=True)
        destination = LOCAL_IMPORTS / (Path(object_key).name)
        if local_path.resolve() != destination.resolve():
            os.replace(local_path, destination)
        return str(destination.relative_to(BASE))

    client, bucket = _client()
    key = object_key.lstrip("/")
    # Stay below the provider's free storage allowance by default. The bucket
    # should be dedicated to CAPFind source PDFs; this is a safety guard, not
    # a billing guarantee if the bucket is used outside this application.
    max_bytes = int(os.getenv("CET_S3_MAX_STORED_BYTES", str(8 * 1024**3)))
    projected = local_path.stat().st_size
    token = None
    while True:
        args = {"Bucket": bucket, "Prefix": "imports/"}
        if token:
            args["ContinuationToken"] = token
        page = client.list_objects_v2(**args)
        projected += sum(int(obj.get("Size", 0)) for obj in page.get("Contents", []))
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    if projected > max_bytes:
        raise StorageNotConfigured(
            f"Source storage quota reached ({projected:,} bytes would exceed "
            f"the configured {max_bytes:,}-byte cap). Delete old source PDFs or "
            "raise CET_S3_MAX_STORED_BYTES only after reviewing free-tier limits."
        )
    # Source PDFs are uploaded on the 100 MiB web instance. boto3's managed
    # upload_file uses multipart concurrency by default and can buffer several
    # parts at once. A single streaming PutObject is bounded and is well below
    # S3's 5 GiB single-PUT limit for CAPFind's 100 MiB CSV / 50 MiB PDF limits.
    with local_path.open("rb") as body:
        client.put_object(
            Bucket=bucket, Key=key, Body=body, ContentLength=local_path.stat().st_size,
            ContentType=("text/csv; charset=utf-8" if Path(object_key).suffix.lower() == ".csv" else "application/pdf"),
            Metadata={"sha256": sha256},
        )
    return f"s3://{bucket}/{quote(key, safe='/')}"


@contextmanager
def materialize_source(stored_path: str):
    """Yield a local path for a stored source and clean up temporary downloads."""
    value = str(stored_path or "")
    if value.startswith("local://"):
        raise FileNotFoundError("This source belongs to the retired local-worker flow")
    if value.startswith("gdrive://"):
        raise FileNotFoundError(
            "Legacy Google Drive imports are no longer supported; upload the PDF directly again"
        )

    if not value.startswith("s3://"):
        path = (BASE / value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Stored source PDF is missing: {path.name}")
        yield path
        return

    bucket, key = _parse_object_uri(value)
    client, configured_bucket = _client()
    if bucket != configured_bucket:
        raise StorageNotConfigured("Source object references a bucket outside the configured private bucket")
    fd, temp_name = tempfile.mkstemp(prefix="cetfind-source-", suffix=".pdf")
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            with temp_path.open("wb") as output:
                while True:
                    chunk = body.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
        finally:
            body.close()
        yield temp_path
    finally:
        temp_path.unlink(missing_ok=True)


def delete_source(stored_path: str) -> None:
    value = str(stored_path or "")
    if not value or value.startswith("local://"):
        return
    if value.startswith("gdrive://"):
        # Never attempt to manage or delete the user's original Drive file.
        raise ValueError("Legacy Google Drive source is external; re-upload it before managing source storage")
    if value.startswith("s3://"):
        bucket, key = _parse_object_uri(value)
        client, configured_bucket = _client()
        if bucket != configured_bucket:
            raise StorageNotConfigured("Refusing to delete an object outside the configured private bucket")
        client.delete_object(Bucket=bucket, Key=key)
        return
    path = (BASE / value).resolve()
    # Restrict local deletion to the application's import storage directory.
    allowed = (BASE / "data" / "imports").resolve()
    if allowed not in path.parents:
        raise ValueError("Refusing to delete a source outside the import storage directory")
    path.unlink(missing_ok=True)
