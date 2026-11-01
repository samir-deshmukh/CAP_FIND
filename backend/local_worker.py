"""CAPFind PDF extraction worker with legacy local upload and outbound queue modes.

For remote panel access, the worker polls CAPFind over HTTPS, downloads a
private queued source PDF, and returns only its extracted artifact. The local
HTTP API remains loopback-only for jobs created by older admin pages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.admin.pipeline import (
    SUPPORTED_COURSE_FAMILIES,
    detect_data_type,
    extract_pdf_metadata,
    identify,
    security_check,
)
from scripts.cutoff_extractor import process_single_pdf as extract_cutoffs
from scripts.seat_matrix_extractor import process_single_pdf as extract_seats

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "local_worker"
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(DATA, 0o700)
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_ARTIFACT_BYTES = 150 * 1024 * 1024
ALLOWED_HOSTS = {"cetfind.onrender.com", "cetfind-backend.onrender.com", "localhost", "127.0.0.1"}
ALLOWED_ORIGINS = {
    "https://cetfind.onrender.com",
    "https://cetfind-backend.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
TERMINAL = {"DONE", "FAILED", "CANCELLED"}
LOCK = threading.RLock()
JOBS: dict[int, dict] = {}
ACTIVE_JOB: int | None = None

app = FastAPI(title="CAPFind Local Extraction Worker", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Content-Length"],
    # Brave/Chromium send this on a cross-origin request from the hosted admin
    # page to this loopback-only service. Starlette rejects it unless this is
    # enabled at preflight time; adding the response header after that check
    # (the old custom middleware) still left the preflight at HTTP 400.
    allow_private_network=True,
)


def _origin_ok(request: Request) -> None:
    origin = request.headers.get("origin", "")
    if origin not in ALLOWED_ORIGINS:
        raise HTTPException(403, "Origin is not allowed to use the CAPFind local worker")


def _backend_ok(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise HTTPException(400, "Backend URL must use HTTPS")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(400, "Backend host is not allow-listed")
    return value.rstrip("/")


def _write_state(job_id: int, state: dict) -> None:
    folder = DATA / f"job_{job_id}"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    tmp = folder / "job.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(folder / "job.json")
    JOBS[job_id] = state


def _load_state(job_id: int) -> dict:
    with LOCK:
        state = JOBS.get(job_id)
        if state:
            return state
        path = DATA / f"job_{job_id}" / "job.json"
        if not path.exists():
            raise HTTPException(404, "Local job not found")
        state = json.loads(path.read_text(encoding="utf-8"))
        JOBS[job_id] = state
        return state


def _remote(state: dict, suffix: str, *, payload=None, files=None, data=None):
    url = state["backend_url"] + f"/admin/api/local-imports/{state['job_id']}/{suffix}"
    response = requests.post(
        url,
        headers={"Authorization": "Bearer " + state["upload_token"]},
        json=payload,
        files=files,
        data=data,
        timeout=(15, 300),
    )
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    if response.status_code >= 400:
        raise RuntimeError(f"CAPFind server returned {response.status_code}: {response.text[:800]}")
    return response.json() if response.content else {}


def _remote_get(state: dict, suffix: str):
    url = state["backend_url"] + f"/admin/api/local-imports/{state['job_id']}/{suffix}"
    response = requests.get(
        url, headers={"Authorization": "Bearer " + state["upload_token"]},
        timeout=(10, 20),
    )
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    if response.status_code >= 400:
        raise RuntimeError(f"CAPFind server returned {response.status_code}: {response.text[:800]}")
    return response.json() if response.content else {}


def _wait_for_server_staging(state: dict) -> dict:
    """Keep the single-job worker queue occupied through server staging.

    Artifact receipt is asynchronous on the server. Starting the next PDF as
    soon as the upload returns lets extraction overlap with staging and keeps
    multiple large sets of temporary files alive at once.
    """
    while True:
        try:
            result = _remote_get(state, "status")
        except requests.RequestException as exc:
            _status(state, "WAITING_FOR_SERVER",
                    "Extracted CSV is uploaded; waiting for CAPFind to resume staging",
                    server_error=str(exc)[:500])
            time.sleep(5)
            continue
        status = str(result.get("status") or "").upper()
        if status in {"STAGED", "REVIEW_REQUIRED", "FAILED", "CANCELLED", "COMPLETED"}:
            return result
        message = str(result.get("message") or "Validation and staging are still queued")
        _status(state, "STAGING", message, server_status=status)
        time.sleep(3)


def _cleanup_extraction_outputs(outdir: Path, keep_artifact: Path) -> None:
    """Remove extractor intermediates but retain the source and retry CSV."""
    keep = keep_artifact.absolute()
    for child in outdir.iterdir():
        if child.absolute() == keep:
            continue
        if child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _finish_server_staging(state: dict) -> None:
    result = _wait_for_server_staging(state)
    status = str(result.get("status") or "").upper()
    artifact_value = str(state.get("artifact_path") or "")
    artifact = Path(artifact_value) if artifact_value else None
    if artifact and artifact.is_file():
        _cleanup_extraction_outputs(artifact.parent, artifact)
    if status in {"STAGED", "REVIEW_REQUIRED", "COMPLETED"}:
        if state.get("remote_worker"):
            # Remote mode retains the source in private server storage.
            # Remove the worker's duplicate PDF and CSV only after staging.
            folder = DATA / f"job_{int(state['job_id'])}"
            for name in {Path(state.get("filename") or "source.pdf").name, "source.pdf"}:
                (folder / name).unlink(missing_ok=True)
            if artifact:
                artifact.unlink(missing_ok=True)
        _status(state, "DONE", f"CAPFind finished validation and staging: {status}",
                server_status=status)
    elif status == "CANCELLED":
        _status(state, "CANCELLED", "CAPFind cancelled validation and staging",
                server_status=status)
    else:
        message = str(result.get("error") or "CAPFind validation or staging failed")
        _status(state, "FAILED", message[:3000], server_status=status)


def _status(state: dict, status: str, message: str, **extra):
    state.update({"status": status, "message": message, "updated_at": time.time(), **extra})
    _write_state(state["job_id"], state)


def _progress(state: dict, page: int, total: int, worker_state: str = "RUNNING"):
    _remote(state, "progress", payload={"page": page, "total": total, "state": worker_state})


def _process_job(job_id: int):
    global ACTIVE_JOB
    state = _load_state(job_id)
    folder = DATA / f"job_{job_id}"
    pdf_path = folder / Path(state["filename"]).name
    if not pdf_path.exists() and (folder / "source.pdf").exists():
        # Recover jobs created by early local-worker builds without losing the source.
        pdf_path = folder / "source.pdf"
    control = folder / "control"
    control.mkdir(exist_ok=True)
    outdir = folder / "artifacts"
    outdir.mkdir(exist_ok=True)
    monitor_stop = threading.Event()
    monitor = threading.Thread(target=_monitor_job_progress,
                               args=(state, control, monitor_stop), daemon=True,
                               name=f"capfind-progress-{job_id}")
    try:
        _status(state, "EXTRACTING", "Checking the PDF on this PC")
        os.environ["CAPFIND_JOB_CONTROL_DIR"] = str(control)
        monitor.start()
        size, actual_sha = security_check(pdf_path)
        if actual_sha != state["sha256"] or size != state["size_bytes"]:
            raise RuntimeError("The local PDF fingerprint does not match the queued import")
        _, filename_family, filename_year, filename_round, _ = identify(state["filename"])
        data_type = detect_data_type(pdf_path, state["filename"], use_ocr=True)
        pdf_family, pdf_year, pdf_round = extract_pdf_metadata(
            pdf_path, state["filename"], use_ocr=True
        )
        # The document's own title and CAP metadata are authoritative. Names
        # are often generic or misleading, so use them only when PDF text did
        # not provide a value (for example, for a scanned document).
        family = pdf_family or filename_family
        year = pdf_year or filename_year
        round_name = pdf_round or filename_round
        if family not in SUPPORTED_COURSE_FAMILIES or not year:
            raise RuntimeError(
                "Could not identify the course family or academic year from the PDF text, "
                "OCR, or filename. Check that the document contains a readable CAP course "
                "heading and academic year, then retry."
            )
        if data_type == "CUTOFFS" and round_name not in {"C1", "C2", "C3", "C4"}:
            raise RuntimeError(
                "Could not identify CAP round C1-C4 from the PDF text, OCR, or filename. "
                "Check that the document contains a readable CAP round heading, then retry."
            )
        _status(state, "EXTRACTING", f"Extracting {data_type} locally · {family} · {year}",
                data_type=data_type, family=family, year=year, round_name=round_name)
        if data_type == "CUTOFFS":
            summary = extract_cutoffs(pdf_path=pdf_path, outdir=outdir, dpi=300, lang="eng", use_camelot=False)
            artifact = outdir / f"{pdf_path.stem}_cutoffs.csv"
            artifact_type = "CUTOFFS"
        else:
            summary = extract_seats(pdf_path=pdf_path, outdir=outdir, dpi=200, lang="eng",
                                    use_ocr=True, force_ocr=False, write_json=False)
            artifact = outdir / f"{pdf_path.stem}_seats_long.csv"
            artifact_type = "SEATS"
        if not artifact.is_file() or artifact.stat().st_size <= 0:
            raise RuntimeError("The extractor did not produce a non-empty CSV artifact")
        if artifact.stat().st_size > MAX_ARTIFACT_BYTES:
            raise RuntimeError("Extracted CSV exceeds the 150 MiB transfer limit")
        _status(state, "UPLOADING", "Uploading extracted CSV to CAPFind for validation",
                artifact_bytes=artifact.stat().st_size, summary=summary)
        with artifact.open("rb") as handle:
            _remote(
                state, "artifact",
                files={"file": (artifact.name, handle, "text/csv")},
                data={
                    "data_type": artifact_type,
                    "family": family,
                    "year": str(year),
                    "round_name": round_name or "",
                    "source_sha256": actual_sha,
                    "summary_json": json.dumps(summary, ensure_ascii=False),
                },
            )
        monitor_stop.set()
        if monitor.ident is not None:
            monitor.join(timeout=2)
        _status(state, "STAGING", "Extraction uploaded; waiting for CAPFind validation and staging",
                summary=summary, artifact_uploaded=True, artifact_path=str(artifact))
        _finish_server_staging(state)
    except Exception as exc:
        if "CAPFIND_WORKER_CANCELLED" in str(exc) or (control / "CANCEL").exists():
            _status(state, "CANCELLED", "Extraction cancelled by the administrator")
            try:
                _remote(state, "cancel")
            except Exception:
                pass
        else:
            _status(state, "FAILED", str(exc)[:3000])
            try:
                _remote(state, "fail", payload={"error": str(exc)[:3000]})
            except Exception:
                pass
    finally:
        monitor_stop.set()
        if monitor.ident is not None:
            monitor.join(timeout=2)
        os.environ.pop("CAPFIND_JOB_CONTROL_DIR", None)
        with LOCK:
            ACTIVE_JOB = None


def _monitor_job_progress(state: dict, control: Path, stop: threading.Event) -> None:
    """Keep the server informed even while PDF metadata/OCR has no page file yet."""
    last_sent = 0.0
    while not stop.wait(1.0):
        progress_path = control / "progress.json"
        try:
            if state.get("remote_worker"):
                # The import panel can be open on any device. Poll the
                # server-side state so remote pause/cancel reaches this worker.
                remote_status = _remote_get(state, "status").get("status")
                if remote_status == "CANCELLED":
                    (control / "CANCEL").touch()
                elif remote_status == "PAUSED":
                    (control / "PAUSE").touch()
                elif remote_status in {"EXTRACTING", "NORMALIZING", "VALIDATING", "COMPARING"}:
                    (control / "PAUSE").unlink(missing_ok=True)
            worker_state = "PAUSED" if state.get("status") == "PAUSED" else "RUNNING"
            if progress_path.exists():
                progress = json.loads(progress_path.read_text(encoding="utf-8"))
                state.update(page=int(progress.get("page", 0)), total=int(progress.get("total", 0)))
                worker_state = str(progress.get("state", "RUNNING"))
                if worker_state == "PAUSED":
                    state.update(status="PAUSED", message=f"Paused at page {state['page']} of {state['total']}")
                elif state.get("status") == "PAUSED":
                    state.update(status="EXTRACTING", message=f"Resumed at page {state['page']} of {state['total']}")
            if time.time() - last_sent >= 15:
                _progress(state, int(state.get("page") or 0), int(state.get("total") or 0), worker_state)
                last_sent = time.time()
            _write_state(int(state["job_id"]), state)
        except Exception:
            # Progress reporting is best-effort; it must never interrupt parsing.
            pass


def _recover_jobs():
    for path in sorted(DATA.glob("job_*/job.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            job_id = int(state["job_id"])
            JOBS[job_id] = state
            if state.get("remote_worker") and state.get("status") in {"QUEUED", "EXTRACTING", "UPLOADING"}:
                # Let the server lease expire and issue a fresh one-job token on
                # the next claim. Reusing a token from before a crash can race
                # with another worker reclaiming the same source.
                state["status"] = "WAITING_FOR_SERVER"
                state["message"] = "Recovered after worker restart; waiting for the server to requeue this job"
                _write_state(job_id, state)
            elif state.get("artifact_uploaded") and state.get("status") in {"STAGING", "WAITING_FOR_SERVER"}:
                state["status"] = "QUEUED"
                state["message"] = "Recovered after worker restart; waiting for CAPFind staging to finish"
                _write_state(job_id, state)
            elif state.get("status") in {"QUEUED", "EXTRACTING", "UPLOADING"}:
                # The extractor does not serialize all in-memory parser state;
                # after a worker crash, safely restart the PDF from page one.
                control = DATA / f"job_{job_id}" / "control"
                (control / "PAUSE").unlink(missing_ok=True)
                (control / "CANCEL").unlink(missing_ok=True)
                state["status"] = "QUEUED"
                state["message"] = "Recovered after worker restart; extraction will restart from page one"
                _write_state(job_id, state)
        except Exception:
            # A corrupt local job record should not prevent the other jobs starting.
            continue


@app.on_event("startup")
def startup():
    _recover_jobs()
    threading.Thread(target=_queue_loop, daemon=True, name="capfind-local-queue").start()


def _queue_loop():
    global ACTIVE_JOB
    next_remote_poll = 0.0
    while True:
        with LOCK:
            if ACTIVE_JOB is None:
                queued = sorted(
                    (job_id for job_id, state in JOBS.items() if state.get("status") == "QUEUED")
                )
                if queued:
                    ACTIVE_JOB = queued[0]
                    job_id = ACTIVE_JOB
                else:
                    job_id = None
            else:
                job_id = None
        if job_id is not None:
            state = _load_state(job_id)
            if state.get("artifact_uploaded"):
                try:
                    _finish_server_staging(state)
                finally:
                    with LOCK:
                        if ACTIVE_JOB == job_id:
                            ACTIVE_JOB = None
            else:
                _process_job(job_id)
        else:
            if time.time() >= next_remote_poll:
                try:
                    claimed = _claim_remote_job()
                    next_remote_poll = time.time() + (5 if claimed else 10)
                except Exception:
                    # Remote mode is optional for backward compatibility with
                    # browser-local installs that do not have the shared secret.
                    next_remote_poll = time.time() + 30
                    log.warning("Remote worker poll failed; retrying in 30 seconds", exc_info=True)
            time.sleep(0.5)


def _claim_remote_job() -> bool:
    backend_url = os.getenv("CAPFIND_BACKEND_URL", "https://cetfind.onrender.com").strip().rstrip("/")
    worker_token = os.getenv("CAPFIND_REMOTE_WORKER_TOKEN", "").strip()
    if not worker_token:
        return False
    parsed = urlparse(backend_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise RuntimeError("CAPFIND_BACKEND_URL must be an allow-listed HTTPS CAPFind host")
    worker_id = os.getenv("CAPFIND_REMOTE_WORKER_ID", socket.gethostname()).strip()[:100]
    worker_id = re.sub(r"[^A-Za-z0-9_.-]", "_", worker_id) or "local-worker"
    response = requests.post(
        backend_url + "/admin/api/remote-worker/claim",
        headers={"Authorization": "Bearer " + worker_token},
        json={"worker_id": worker_id}, timeout=(10, 20),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"CAPFind worker queue returned {response.status_code}: {response.text[:800]}")
    payload = response.json()
    job = payload.get("job")
    if not job:
        return False
    job_id = int(job["job_id"])
    filename = Path(str(job["filename"] or "source.pdf")).name
    folder = DATA / f"job_{job_id}"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    state = {
        "job_id": job_id, "filename": filename, "backend_url": backend_url,
        "upload_token": job["upload_token"], "sha256": str(job["sha256"]).lower(),
        "size_bytes": int(job["size_bytes"]), "status": "QUEUED",
        "message": "Claimed from the CAPFind server; downloading the source PDF",
        "created_at": time.time(), "updated_at": time.time(), "remote_worker": True,
    }
    _write_state(job_id, state)
    target = folder / filename
    partial = folder / (filename + ".download")
    lease_stop = threading.Event()

    def keep_lease():
        while not lease_stop.wait(20):
            try:
                _remote_get(state, "status")
            except Exception:
                log.warning("Could not refresh the remote worker lease for job %s", job_id)

    lease_thread = threading.Thread(target=keep_lease, daemon=True, name=f"capfind-download-lease-{job_id}")
    lease_thread.start()
    try:
        source_response = requests.get(
            backend_url + f"/admin/api/remote-worker/jobs/{job_id}/source",
            headers={"Authorization": "Bearer " + job["upload_token"]},
            stream=True, timeout=(15, 300),
        )
        if source_response.status_code >= 400:
            raise RuntimeError(f"Source download returned {source_response.status_code}: {source_response.text[:800]}")
        digest = hashlib.sha256()
        total = 0
        with partial.open("wb") as output:
            for chunk in source_response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise RuntimeError("Remote source PDF exceeds the 50 MiB limit")
                digest.update(chunk)
                output.write(chunk)
        if total != state["size_bytes"] or digest.hexdigest() != state["sha256"]:
            raise RuntimeError("Downloaded source PDF failed the size or SHA-256 integrity check")
        os.chmod(partial, 0o600)
        partial.replace(target)
    except Exception as exc:
        partial.unlink(missing_ok=True)
        _status(state, "FAILED", "Could not download the retained source PDF: " + str(exc)[:2500], error=str(exc)[:2500])
        try:
            _remote(state, "fail", payload={"error": "Remote worker could not download the retained source PDF: " + str(exc)[:2500]})
        except Exception:
            log.exception("Could not report remote source download failure for job %s", job_id)
        return True
    finally:
        lease_stop.set()
        lease_thread.join(timeout=2)
    _status(state, "QUEUED", "Source PDF downloaded and verified; queued for extraction")
    global ACTIVE_JOB
    with LOCK:
        ACTIVE_JOB = job_id
    _process_job(job_id)
    return True


@app.get("/health")
def health():
    with LOCK:
        return {"ok": True, "worker": "CAPFind Local Extraction Worker", "active_job": ACTIVE_JOB,
                "queued_jobs": sum(s.get("status") == "QUEUED" for s in JOBS.values())}


@app.get("/jobs/{job_id}")
def job_status(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    return {k: state.get(k) for k in ("job_id", "status", "message", "page", "total", "updated_at", "error")}


@app.post("/jobs", status_code=202)
async def enqueue_job(
    request: Request,
    file: UploadFile = File(...),
    job_id: int = Form(...),
    backend_url: str = Form(...),
    upload_token: str = Form(...),
    expected_sha256: str = Form(...),
    expected_size: int = Form(...),
):
    _origin_ok(request)
    backend_url = _backend_ok(backend_url)
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise HTTPException(400, "Invalid PDF SHA-256")
    if expected_size < 5 or expected_size > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF size is invalid or exceeds 50 MiB")
    if not upload_token or len(upload_token) > 256:
        raise HTTPException(400, "Invalid one-job authorization token")
    folder = DATA / f"job_{job_id}"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    safe_filename = Path(file.filename or "source.pdf").name
    pdf_path = folder / safe_filename
    tmp_path = folder / (safe_filename + ".upload")
    digest = hashlib.sha256()
    total = 0
    try:
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise HTTPException(413, "PDF exceeds 50 MiB")
                digest.update(chunk)
                out.write(chunk)
        if total != expected_size or digest.hexdigest() != expected_sha256.lower():
            raise HTTPException(400, "PDF size or fingerprint does not match the CAPFind import")
        with tmp_path.open("rb") as inp:
            if inp.read(5) != b"%PDF-":
                raise HTTPException(400, "File is not a valid PDF")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(pdf_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    state = {
        "job_id": job_id, "filename": Path(file.filename or "source.pdf").name,
        "backend_url": backend_url, "upload_token": upload_token,
        "sha256": expected_sha256.lower(), "size_bytes": expected_size,
        "status": "QUEUED", "message": "Saved locally; queued for extraction",
        "created_at": time.time(), "updated_at": time.time(),
    }
    with LOCK:
        if job_id in JOBS and JOBS[job_id].get("status") not in TERMINAL:
            raise HTTPException(409, "This local job is already queued or running")
        _write_state(job_id, state)
    return {"ok": True, "job_id": job_id, "status": "QUEUED"}


@app.post("/jobs/{job_id}/pause")
def pause_job(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    if state.get("status") not in {"QUEUED", "EXTRACTING"}:
        raise HTTPException(409, "Only queued or extracting jobs can be paused")
    control = DATA / f"job_{job_id}" / "control"
    control.mkdir(exist_ok=True)
    (control / "PAUSE").touch()
    _status(state, "PAUSED", "Pause requested; the worker will stop at the next page checkpoint")
    return {"ok": True, "status": "PAUSED"}


@app.post("/jobs/{job_id}/resume")
def resume_job(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    if state.get("status") != "PAUSED":
        raise HTTPException(409, "Only paused jobs can be resumed")
    control = DATA / f"job_{job_id}" / "control"
    (control / "PAUSE").unlink(missing_ok=True)
    # A paused job that has not entered its first page checkpoint is still queued.
    resume_status = "QUEUED" if state.get("page") is None else "EXTRACTING"
    _status(state, resume_status, "Resume requested")
    return {"ok": True, "status": resume_status}


@app.post("/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    if state.get("status") not in {"FAILED", "CANCELLED", "DONE"}:
        raise HTTPException(409, "Only failed/cancelled extraction jobs or completed extractions can be retried")
    control = DATA / f"job_{job_id}" / "control"
    (control / "PAUSE").unlink(missing_ok=True)
    (control / "CANCEL").unlink(missing_ok=True)
    try:
        if state.get("status") == "DONE":
            try:
                _remote(state, "revalidate")
            except RuntimeError as exc:
                # A Render deploy can replace the server after it received the
                # CSV but before validation/staging completed. The local copy is
                # durable on this PC, so resend it if the server copy was lost.
                if "returned 404:" not in str(exc):
                    raise
                data_type = str(state.get("data_type") or "").upper()
                suffix = "_cutoffs.csv" if data_type == "CUTOFFS" else "_seats_long.csv"
                artifact = DATA / f"job_{job_id}" / "artifacts" / f"{Path(state['filename']).stem}{suffix}"
                if not artifact.is_file():
                    raise RuntimeError("The saved extracted CSV is missing on this PC; retry extraction from the source PDF") from exc
                with artifact.open("rb") as handle:
                    _remote(
                        state, "artifact",
                        files={"file": (artifact.name, handle, "text/csv")},
                        data={
                            "data_type": data_type,
                            "family": str(state.get("family") or ""),
                            "year": str(state.get("year") or ""),
                            "round_name": str(state.get("round_name") or ""),
                            "source_sha256": state["sha256"],
                            "summary_json": json.dumps(state.get("summary") or {}, ensure_ascii=False),
                        },
                    )
            state.update(status="DONE", message="Server validation retry started using the saved extracted CSV",
                         updated_at=time.time())
            _write_state(job_id, state)
            return {"ok": True, "status": "DONE"}
        _remote(state, "restart")
    except Exception as exc:
        raise HTTPException(502, str(exc)[:800])
    state.update(status="QUEUED", message="Retry queued; extraction restarts from page one",
                 page=0, total=0, error=None, updated_at=time.time())
    _write_state(job_id, state)
    return {"ok": True, "status": "QUEUED"}


@app.delete("/jobs/{job_id}")
def delete_local_job(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    if state.get("status") not in TERMINAL:
        raise HTTPException(409, "Cancel or finish the local job before deleting its source PDF")
    with LOCK:
        shutil.rmtree(DATA / f"job_{job_id}", ignore_errors=True)
        JOBS.pop(job_id, None)
    return {"ok": True, "job_id": job_id, "deleted": True}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: int):
    _origin_ok(request)
    state = _load_state(job_id)
    if state.get("status") in TERMINAL:
        raise HTTPException(409, "Job is already finished")
    control = DATA / f"job_{job_id}" / "control"
    control.mkdir(exist_ok=True)
    (control / "CANCEL").touch()
    _status(state, "CANCELLED", "Cancellation requested; the worker will stop at the next page checkpoint")
    # A queued job may not enter the extractor loop, so notify Render here as well.
    try:
        _remote(state, "cancel")
    except Exception as exc:
        state["message"] = "Stopped locally; server cancellation sync will need a retry: " + str(exc)[:300]
        _write_state(job_id, state)
        raise HTTPException(502, state["message"])
    return {"ok": True, "status": "CANCELLED"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.local_worker:app", host="127.0.0.1", port=8765, log_level="info")
