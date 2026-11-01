# CAPFind Remote Extraction Worker

## How remote panel use works

- Admins can open Import Center from any device and upload PDFs to the authenticated CAPFind API.
- The API streams each PDF to private S3-compatible storage. It does not keep the entire PDF in Render RAM.
- The worker PC makes outbound HTTPS requests to claim jobs and download the source PDF. No browser-to-PC connection, local-network permission, public worker port, or tunnel is needed.
- The worker verifies the source size and SHA-256, runs the existing cutoff and seat-matrix extractors on the PC, and uploads the extracted CSV and audit summary to CAPFind.
- The worker processes one PDF through server validation and staging before starting the next queued PDF. It removes extractor intermediates after artifact upload; in remote queue mode, it also removes its local source and CSV copies after successful staging because the source remains in private storage.
- CAPFind continues normalization, validation, duplicate comparison, staging, review, and approval on the server. Extraction never approves or publishes data.
- Source PDFs must be in private, durable storage. Remote PDF upload fails closed unless S3-compatible storage and the worker secret are configured. Render's local filesystem is not a safe queue because a deploy or restart can remove queued source files.

The local worker HTTP service still binds only to **127.0.0.1:8765** for compatibility with already queued legacy jobs. The remote queue uses outbound HTTPS and does not expose this service to the LAN or internet.

## One-time setup

On Render, configure:

- `CET_PDF_STORAGE_BACKEND=s3`
- `CET_S3_ENDPOINT_URL`, `CET_S3_BUCKET`, `CET_S3_ACCESS_KEY_ID`, and `CET_S3_SECRET_ACCESS_KEY` for a private bucket
- `CAPFIND_REMOTE_WORKER_TOKEN` as a random secret with at least 32 characters

Generate a shared token locally with `openssl rand -hex 32`, then enter the same value in Render and the worker PC. Use a bucket dedicated to CAPFind source PDFs, keep it private, and review the provider's storage and request limits. Never put these values in Git or a support message. The existing storage quota guard remains active.

On the worker PC, create a virtual environment and install the worker dependencies if not already present:

```bash
python3 -m venv ~/.venvs/capfind-local-worker
~/.venvs/capfind-local-worker/bin/python -m pip install -r requirements-dev.txt
```

Edit `~/.config/capfind/local-worker.env` and set `CAPFIND_REMOTE_WORKER_TOKEN` to the same random value configured on Render. Keep the file owner-readable only. `CAPFIND_BACKEND_URL` defaults to `https://cetfind.onrender.com` and can be changed if the backend host changes.

Install or update the automatically restarting user service from the `cet/` directory:

```bash
scripts/install_local_worker_service.sh
```

Check it with `systemctl --user status capfind-local-worker.service`. Logs are available with `journalctl --user -u capfind-local-worker.service`. After changing the env file, restart with `systemctl --user restart capfind-local-worker.service`.

## Availability and controls

- The PC must be powered on, connected to the internet, and logged into the worker user's desktop session. The worker reconnects to the queue after a network interruption or service restart.
- If the PC is offline, uploaded PDFs remain in private durable storage and wait in the queue. The Import Center shows the worker as offline.
- Pause and cancel commands are read from the server at safe extraction checkpoints, so the admin can control jobs from another device.
- A worker restart may restart extraction from page one because parser state is not serializable. It retains the original PDF and checks the hash before processing. Existing staged data is not silently discarded by recovery.
- Retry after a server validation failure reuses the retained CSV when it is still available; a retry after worker failure downloads the retained source PDF again.
- Legacy same-PC mode retains the original PDF and final CSV for retries. If those retained files themselves fill the PC disk, queueing cannot reclaim that durable data; configure private S3-compatible storage and remote worker mode, or remove completed imports through the admin workflow.

## OCR dependency

`pytesseract` is a Python wrapper, not the Tesseract OCR executable. If PDFs contain scanned pages, install the operating-system package `tesseract-ocr` on the worker PC and ensure `tesseract` is on PATH. Without it, extraction continues using native PDF text, but OCR-only pages may not produce records.

## Security and data handling

- Only authorized CAPFind admins can create jobs. PDF bytes are streamed to private storage and are never exposed through a public URL.
- The Render server and worker share a long random secret used only for worker queue claims. Each claimed job also gets a separate random bearer token; the server stores only its SHA-256 hash.
- The worker downloads only jobs returned by the authenticated claim endpoint. It verifies the source PDF SHA-256 and size before extraction. The server checks the same source fingerprint when it receives the artifact.
- The S3-compatible bucket stores source PDFs; the worker PC keeps its processing files under the git-ignored `data/local_worker/` directory. Admin source deletion removes the stored source through the existing private storage adapter.

## Course identification

Course family, academic year, and CAP round are read from the PDF's native text before the filename is used. The identifier samples up to 24 pages so a cover or notice page does not hide the CAP heading. If native text cannot identify the family or year, the worker uses Tesseract OCR on the first four pages. This supports generic or randomized PDF filenames when the document itself contains a readable CAP heading. If identification still fails, the import reports the missing field for review instead of guessing.
