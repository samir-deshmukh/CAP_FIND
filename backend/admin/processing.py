"""
Part 2: real PDF -> extracted artifacts -> validation -> staging.

This module deliberately calls the existing, trusted CET extractors and
validation gates rather than reimplementing their parsing rules. Production
fact tables are NOT modified here.
"""
from __future__ import annotations
import csv, importlib.util, json, shutil, subprocess, sys, os, time
from functools import lru_cache
from pathlib import Path
from .db import connect, event, update_status
from .state import JobStatus, can_transition

BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
WORK_ROOT = BASE / "data" / "import_work"
STAGING_ROOT = BASE / "data" / "import_staging"

class ImportCancelled(Exception):
    pass

def _cancel_marker(job_id: int) -> Path:
    return STAGING_ROOT / f"job_{job_id}" / "CANCEL"

def _cancel_requested(job_id: int) -> bool:
    return _cancel_marker(job_id).exists()

def _raise_if_cancelled(conn, job_id: int) -> None:
    row = conn.execute('SELECT status FROM import_jobs WHERE id=?', (job_id,)).fetchone()
    if not _cancel_requested(job_id) and (not row or row.get('status') != JobStatus.CANCELLED.value):
        return
    conn.execute(
        "UPDATE import_jobs SET status=?, error_message=NULL, updated_at=CURRENT_TIMESTAMP "
        "WHERE id=? AND status NOT IN ('COMPLETED','COMMITTING','PUBLISHING','VERIFYING','CANCELLED')",
        (JobStatus.CANCELLED.value, job_id),
    )
    event(conn, job_id, "CANCELLED", "Processing stopped by admin", None)
    conn.commit()
    raise ImportCancelled()

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load extractor: {path.name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _run_validator(script: Path, folder: Path) -> tuple[bool, str]:
    env = os.environ.copy()
    # Validation scripts emit Unicode audit markers. Force UTF-8 so the same
    # subprocess behaves identically on Windows development machines and
    # Linux/Render production instead of failing on CP1252 stdout.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    p = subprocess.run(
        [sys.executable, str(script), str(folder)],
        cwd=str(BASE), capture_output=True, text=True, timeout=900, env=env
    )
    output = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, output

def _canonical_cutoff_name(family: str, year: int, round_name: str) -> str:
    return f"{family}_{str(year)[-2:]}_{round_name}_cutoffs.csv"

def _canonical_seat_name(family: str) -> str:
    return f"{family}_SM.csv"

def _page_from(row: dict):
    v = str(row.get("page", "")).strip()
    return int(v) if v.isdigit() else None

def _resolve_cutoff_dimensions(raw: dict):
    """Resolve cutoff category/section/stage without inventing source context.

    The trusted validator deliberately accepts a blank section (the category
    suffix already encodes H/O/S) and maps a blank stage to the explicit
    canonical value Unknown. The import path must use the same semantics;
    otherwise a historically clean PDF can be quarantined merely because a
    table's merged/visually inherited cell is blank in the CSV.
    """
    from scripts.category_codes import is_category_code
    from scripts.validate_data import SECTION_MAP, STAGE_MAP, parse_category

    category = str(raw.get("category", "")).strip()
    base, ladies, derived_section = parse_category(category)
    if base is None or not is_category_code(category):
        raise ValueError(f"Malformed category code: {category!r}")

    section_raw = str(raw.get("section", "")).strip()
    if section_raw:
        section = SECTION_MAP.get(section_raw)
        if section is None:
            raise ValueError(f"Unknown section: {section_raw!r}")
    else:
        section = derived_section
    if section is None:
        raise ValueError(f"Unable to resolve section for category: {category!r}")

    stage_raw = str(raw.get("stage", "")).strip()
    if stage_raw:
        stage = STAGE_MAP.get(stage_raw)
        if stage is None:
            raise ValueError(f"Unknown stage: {stage_raw!r}")
    else:
        stage = STAGE_MAP[""]

    return base, ladies, section, stage

def _csv_control_checkpoint(conn, job_id: int) -> None:
    """Honor stop/pause controls while a large CSV is being staged."""
    import time
    pause_marker = STAGING_ROOT / f"job_{job_id}" / "PAUSE"
    while pause_marker.exists():
        _raise_if_cancelled(conn, job_id)
        time.sleep(0.25)
    _raise_if_cancelled(conn, job_id)


def _stage_csv(conn, job_id: int, result_type: str, path: Path,
               valid: bool, validation_message: str, required_fields=(),
               progress_callback=None, expected_rows: int | None = None) -> tuple[int, int]:
    rows = 0
    quarantined = 0
    total_rows = 0
    if progress_callback:
        try:
            expected = int(expected_rows or 0)
        except (TypeError, ValueError):
            expected = 0
        if expected > 0:
            # Extractors already report the number of emitted records. Reuse
            # that count instead of parsing a large CSV just to calculate progress.
            total_rows = expected
        else:
            # For uploaded CSVs without an extractor summary, count records
            # (not physical lines, since quoted fields can contain newlines).
            with path.open("r", encoding="utf-8-sig", newline="") as count_file:
                total_rows = max(0, sum(1 for _ in csv.DictReader(count_file)))
        try:
            progress_callback(0, total_rows)
        except Exception:
            pass
    # Progress is persisted using a separate database connection. Keep updates
    # coarse enough that telemetry does not become a material part of staging
    # time for large PDFs.
    progress_interval = max(5000, total_rows // 20) if total_rows else 5000
    # The trusted validator treats these columns as block-level merged cells:
    # a blank value means "same as the preceding row". Apply the same
    # normalization before staging so continuation pages do not become false
    # missing-field errors, while preserving the original row in raw_json.
    fill_columns = (
        "institution_code", "institution_name", "program_code",
        "program_name", "status", "section",
    )
    seat_lane_map = seat_alias_map = None
    if result_type == "SEATS":
        from scripts.category_codes import is_category_code
        from scripts.validate_seats import load_whitelists, normalize_category, TOTAL_MARKER
        _, seat_lane_map, seat_alias_map = load_whitelists(BASE / "data" / "reference")
    last_values = {field: "" for field in fill_columns}
    batch = []

    def flush_batch():
        if not batch:
            return
        values_per_row = 8
        placeholders = ",".join(["(" + ",".join(["?"] * values_per_row) + ")"] * len(batch))
        params = tuple(value for record in batch for value in record)
        conn.execute_many_values(
            "INSERT INTO import_staging_records "
            "(job_id,result_type,source_file,source_page,raw_json,normalized_json,validation_status,validation_message) "
            f"VALUES {placeholders}",
            params,
        )
        batch.clear()

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw = dict(row)
            normalized = dict(row)
            for field in fill_columns:
                value = str(normalized.get(field, "")).strip()
                if value:
                    last_values[field] = value
                elif last_values[field]:
                    normalized[field] = last_values[field]
            missing = [field for field in required_fields if not str(normalized.get(field, "")).strip()]
            row_errors = []
            if missing:
                row_errors.append("Missing required field(s): " + ", ".join(missing))
            # A file-level validator failure must not turn every otherwise
            # well-formed row into a separate row error. For cutoff rows, run
            # the same category/section/stage resolver used by commit so only
            # rows with an actual row-level problem are marked REVIEW. The
            # import result remains REVIEW_REQUIRED, so a failed file gate
            # still cannot be committed accidentally.
            if result_type == "CUTOFFS" and not missing:
                try:
                    _resolve_cutoff_dimensions(normalized)
                except (ValueError, KeyError) as exc:
                    row_errors.append(str(exc))
            elif result_type == "SEATS" and not missing:
                lane_raw = str(normalized.get("allocation_type", "")).strip()
                category_raw = str(normalized.get("category", "")).strip()
                if lane_raw not in seat_lane_map:
                    row_errors.append(f"Unknown allocation type: {lane_raw!r}")
                if category_raw.casefold() != TOTAL_MARKER.casefold():
                    if not is_category_code(category_raw):
                        row_errors.append(
                            f"Malformed category code {category_raw!r} at page {_page_from(normalized)}; "
                            "check the source PDF before approval"
                        )
            if row_errors:
                quarantined += 1
                row_status = "REVIEW"
                message = "; ".join(row_errors)
            elif not valid:
                row_status = "FILE_REVIEW"
                message = "File-level validation failed; inspect the validation report before approval."
            else:
                row_status = "VALID"
                message = None
            raw_json = json.dumps(raw, ensure_ascii=False)
            normalized_json = json.dumps(normalized, ensure_ascii=False)
            # NULL means normalization left the source row unchanged. PostgreSQL
            # compresses each TEXT value independently, so retaining both copies
            # needlessly duplicates the row payload.
            batch.append((job_id, result_type, path.name, _page_from(normalized),
                          raw_json,
                          normalized_json if normalized_json != raw_json else None,
                          row_status, message))
            rows += 1
            if len(batch) >= 1000:
                _csv_control_checkpoint(conn, job_id)
                flush_batch()
            if progress_callback and (rows % progress_interval == 0 or (total_rows and rows == total_rows)):
                _csv_control_checkpoint(conn, job_id)
                flush_batch()
                try:
                    progress_callback(rows, total_rows)
                except ImportCancelled:
                    raise
                except Exception:
                    # Telemetry must never interrupt the import itself.
                    pass
    _csv_control_checkpoint(conn, job_id)
    flush_batch()
    if progress_callback:
        try:
            # The emitted CSV can differ slightly from the extractor's
            # estimate after safe cleaning. Publish the exact final count.
            progress_callback(rows, rows)
        except ImportCancelled:
            raise
        except Exception:
            pass
    return rows, quarantined

def _insert_result(conn, job_id, result_type, raw_path, normalized_path,
                   valid, extracted, staged, quarantined, summary):
    conn.execute(
        """INSERT INTO import_results
           (job_id,result_type,raw_artifact_path,normalized_artifact_path,
            validation_status,rows_extracted,rows_validated,rows_quarantined,
            summary_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (job_id,result_type,str(raw_path.relative_to(BASE)),
         str(normalized_path.relative_to(BASE)) if normalized_path else None,
         "PASS" if valid else "REVIEW_REQUIRED",
         extracted, staged if valid else 0, quarantined,
         json.dumps(summary, ensure_ascii=False))
    )


def _compare_cutoffs(conn, path: Path, family: str, year: int, round_name: str) -> dict:
    existing = set()
    q = conn.execute("""SELECT c.institution_code,p.program_name_raw,c.base_category,
                               c.is_ladies,c.section_code,c.stage_code,c.rank_number,c.rank_suffix,c.percentile
                        FROM cutoffs c JOIN programs p ON p.program_id=c.program_id
                        WHERE c.year=? AND c.round=? AND p.program_family=?""",
                     (year, int(round_name[1:]), family))
    for r in q:
        existing.add(tuple(r))
    new_rows = changed = duplicates = 0
    seen = set()
    # A changed cutoff keeps the same institute/program/category/section/stage
    # identity but has a different rank/percentile. It must be surfaced for
    # review, never silently treated as an ordinary new row.
    identity_existing = {}
    for r in existing:
        identity = r[:6]
        identity_existing.setdefault(identity, set()).add((r[6], r[7], r[8]))
    changed_examples = []
    duplicate_in_stage = 0
    uncomparable_rows = 0
    fill_columns = (
        "institution_code", "institution_name", "program_code",
        "program_name", "status", "section",
    )
    last_values = {field: "" for field in fill_columns}
    rows_compared = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = dict(raw_row)
            rows_compared += 1
            for field in fill_columns:
                value = str(row.get(field, "")).strip()
                if value:
                    last_values[field] = value
                elif last_values[field]:
                    row[field] = last_values[field]
            # A malformed category has already been quarantined by _stage_csv.
            # Do not let one bad extracted row abort comparison of a large PDF.
            try:
                base, ladies, section, stage = _resolve_cutoff_dimensions(row)
            except (ValueError, KeyError):
                uncomparable_rows += 1
                continue
            rs = row["rank_suffix"].strip() or None
            rn = int(row["rank_number"]) if row["rank_number"].strip().isdigit() else None
            pct = float(row["percentage"]) if row["percentage"].strip() else None
            key = (row["institution_code"].strip(), row["program_name"].strip(), base,
                   int(bool(ladies)), section, stage, rn, rs, pct)
            identity = key[:6]
            if key in seen:
                duplicate_in_stage += 1
            seen.add(key)
            if key in existing:
                duplicates += 1
            elif identity in identity_existing:
                changed += 1
                if len(changed_examples) < 100:
                    changed_examples.append({"identity": identity, "new": key[6:]})
            else:
                new_rows += 1
    return {"rows_compared": rows_compared, "rows_uncomparable_quarantined": uncomparable_rows,
            "already_present_exact_key": duplicates, "new_candidates": new_rows,
            "changed_candidates": changed, "duplicate_in_staged_input": duplicate_in_stage,
            "changed_examples": changed_examples}

def _compare_seats(conn, path: Path, family: str, year: int) -> dict:
    from scripts.ingest_seats import load_whitelists
    valid_cats, lane_map, alias_map = load_whitelists(BASE / "data" / "reference")
    existing = set(tuple(r) for r in conn.execute(
        """SELECT institution_code,choice_code,allocation_lane,raw_category,raw_gender
           FROM seats WHERE capture_year=? AND program_family=?""", (year,family)))
    duplicates = 0
    rows_compared = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows_compared += 1
            cat = row["category"].strip()
            lane = lane_map.get(row["allocation_type"].strip(), row["allocation_type"].strip())
            key = (row["institution_code"].strip(), row["choice_code"].strip(), lane,
                   cat, row.get("gender", "").strip())
            if key in existing:
                duplicates += 1
    return {"rows_compared": rows_compared, "already_present_exact_key": duplicates,
            "new_candidates": rows_compared - duplicates}

def process_import(conn, job_id: int, pdf_path: Path, *,
                   data_type: str, family: str, year: int, round_name: str,
                   claimed: bool=False, pre_extracted_path: Path | None=None,
                   extraction_summary: dict | None=None, source_filename: str | None=None, worker_id: str | None=None,
                   progress_callback=None):
    """Run extraction/normalization/validation and stop at STAGED/REVIEW_REQUIRED."""
    # Stable per-job work path lets the chunk manifest skip completed parts on retry.
    work = WORK_ROOT / f"job_{job_id}"
    raw = work / "raw"
    normalized = work / "normalized"
    shutil.rmtree(normalized, ignore_errors=True)
    shutil.rmtree(work / "cleaned", ignore_errors=True)
    shutil.rmtree(work / "isolated_project", ignore_errors=True)
    staging = STAGING_ROOT / f"job_{job_id}"
    for d in (raw, normalized, staging):
        d.mkdir(parents=True, exist_ok=True)

    try:
        if not claimed:
            if not can_transition(JobStatus.REVIEW_REQUIRED, JobStatus.EXTRACTING):
                raise RuntimeError("Import state machine does not permit processing from review")
            update_status(conn, job_id, JobStatus.EXTRACTING.value, "Running trusted PDF extractor")
        else:
            event(conn, job_id, "EXTRACT", "Processing job claimed by admin worker", 45)
        event(conn, job_id, "EXTRACT", f"Starting {data_type.lower()} extraction", 45)
        _raise_if_cancelled(conn, job_id)

        if data_type == "CUTOFFS":
            if pre_extracted_path is None:
                # Run bounded page-range extraction in a child process. This keeps
                # the parent API process from retaining the full PDF parser state
                # and allows cooperative pause/cancel checkpoints between pages.
                control_dir = staging
                control_dir.mkdir(parents=True, exist_ok=True)
                env = os.environ.copy()
                env["CAPFIND_JOB_CONTROL_DIR"] = str(control_dir)
                env["CAPFIND_JOB_ID"] = str(job_id)
                env["CAPFIND_WORKER_ID"] = str(worker_id or "")
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                # Keep production extraction chunks bounded to 10 pages for low-memory workers.
                chunk_pages = "10"
                command = [
                    sys.executable, str(SCRIPTS / "chunked_cutoff_extractor.py"),
                    str(pdf_path), "--out", str(raw), "--chunk-pages", chunk_pages,
                    "--source-name", source_filename or pdf_path.name,
                ]
                process = subprocess.run(
                    command, cwd=str(BASE), env=env, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", check=False,
                )
                _raise_if_cancelled(conn, job_id)
                if process.returncode != 0:
                    raise RuntimeError(
                        "Chunked cutoff extraction failed: "
                        + ((process.stderr or process.stdout or "no extractor output")[-3500:])
                    )
                manifest_path = raw / ".chunk_work" / "manifest.json"
                if not manifest_path.is_file():
                    raise RuntimeError("Chunked extractor did not write its completion manifest")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("status") != "COMPLETED":
                    raise RuntimeError("Chunked extractor manifest is not marked COMPLETED")
                summary = dict(manifest.get("result") or {})
                summary["merged_records"] = int(summary.get("rows_extracted", 0))
                extracted_path = raw / f"{pdf_path.stem}_cutoffs.csv"
                if not summary.get("page_coverage_valid"):
                    raise RuntimeError("Chunked extractor failed original-page coverage validation")
            else:
                extracted_path = Path(pre_extracted_path)
                summary = dict(extraction_summary or {})
            _raise_if_cancelled(conn, job_id)
            if not extracted_path.exists():
                raise RuntimeError("Cutoff extractor produced no CSV artifact")
            canonical = normalized / _canonical_cutoff_name(family, year, round_name)
            shutil.copy2(extracted_path, canonical)
            event(conn, job_id, "EXTRACT", f"Extracted {summary.get('merged_records', 0)} cutoff rows", 60)
            update_status(conn, job_id, JobStatus.NORMALIZING.value, "Canonicalizing cutoff artifact")
            event(conn, job_id, "NORMALIZE", f"Normalized artifact: {canonical.name}", 68)

            # Safe cleaner only quarantines genuinely blank categories; it does not
            # guess values. Work in a copy so production/reference data isn't changed
            # during an import job.
            clean_out = work / "cleaned"
            clean_ref = BASE / "data" / "reference"
            # clean_data.py operates on its project reference directory, so invoke it
            # only after copying the project reference into an isolated subprocess cwd.
            isolated = work / "isolated_project"
            (isolated / "data" / "reference").mkdir(parents=True)
            shutil.copytree(BASE / "data" / "reference", isolated / "data" / "reference",
                            dirs_exist_ok=True)
            shutil.copy2(canonical, isolated / "raw.csv")
            # Rather than allowing cleaner path assumptions to touch project files,
            # call its functions directly.
            cleaner = _load_module(SCRIPTS / "clean_data.py", "cet_clean_data")
            cleaner.CATEGORY_WHITELIST_PATH = isolated / "data" / "reference" / "category_whitelist.csv"
            cleaner.CATEGORY_WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE / "data" / "reference" / "category_whitelist.csv",
                         cleaner.CATEGORY_WHITELIST_PATH)
            clean_out.mkdir(parents=True, exist_ok=True)
            rejects = clean_out / "rejects"
            cleaner.clean_file(canonical, clean_out, rejects)
            cleaned = clean_out / canonical.name
            shutil.copy2(cleaned, canonical)
            update_status(conn, job_id, JobStatus.VALIDATING.value, "Running cutoff data quality gate")
            event(conn, job_id, "VALIDATE", "Running existing validate_data.py gate", 78)
            valid, validation = _run_validator(SCRIPTS / "validate_data.py", clean_out)
            # Validator reads project references; its only intended input is the
            # normalized/cleaned CSV. Save its exact output as an audit artifact.
            (work / "validation.txt").write_text(validation, encoding="utf-8")
            quarantine = sum(1 for _ in rejects.glob("*.csv")) if rejects.exists() else 0
            # Section/stage blanks are valid source states: the shared
            # validator maps blank stage -> Unknown and category suffixes
            # deterministically supply section when the visual cell is blank.
            # Only fields that cannot be reconstructed without guessing are
            # required at row level.
            rows, row_quarantine = _stage_csv(
                conn, job_id, "CUTOFFS", canonical, valid, validation,
                ("institution_code", "program_name", "category", "percentage"),
                progress_callback=progress_callback,
                expected_rows=summary.get("merged_records"),
            )
            valid = valid and row_quarantine == 0
            shutil.copy2(canonical, staging / canonical.name)
            shutil.copy2(work / "validation.txt", staging / "validation.txt")
            _insert_result(conn, job_id, "CUTOFFS", extracted_path, canonical,
                           valid, int(summary.get("merged_records", rows)), rows - row_quarantine,
                           quarantine + row_quarantine, {"extractor": summary, "validation": validation[-12000:]})
        else:
            if pre_extracted_path is not None:
                extracted_path = Path(pre_extracted_path)
                summary = dict(extraction_summary or {})
            else:
                # Seat matrices can be hundreds of pages and are substantially more
                # memory-intensive than cutoff PDFs. Run the extractor in a child
                # process so pdfplumber/Pillow/Tesseract allocations are released by
                # the OS when extraction finishes instead of accumulating in the
                # FastAPI web process. The extractor writes the same artifacts as before.
                env = os.environ.copy()
                env.setdefault("PYTHONIOENCODING", "utf-8")
                env.setdefault("PYTHONUTF8", "1")
                env.setdefault("OMP_THREAD_LIMIT", "1")
                env.setdefault("OPENBLAS_NUM_THREADS", "1")
                env.setdefault("MKL_NUM_THREADS", "1")
                # The seat extractor uses cooperative checkpoints too; expose the
                # same progress/control channel used by the chunked cutoff worker.
                env["CAPFIND_JOB_CONTROL_DIR"] = str(staging)
                env["CAPFIND_JOB_ID"] = str(job_id)
                env["CAPFIND_WORKER_ID"] = str(worker_id or "")
                # The extractor closes each PDF page after processing and streams seat rows
                # to disk, so long files need a length-aware watchdog rather than a
                # fixed 30-minute cutoff. Keep a hard ceiling for genuinely stuck jobs.
                try:
                    import fitz
                    with fitz.open(pdf_path) as source_doc:
                        expected_pages = len(source_doc)
                except Exception:
                    expected_pages = 0
                timeout_seconds = max(1800, min(4 * 60 * 60, expected_pages * 15))
                env["CAPFIND_TOTAL_PAGES"] = str(expected_pages)
                # Seat matrices currently run as one page-checkpointed extraction
                # rather than cutoff-style page chunks.
                env["CAPFIND_CHUNK_INDEX"] = "1"
                env["CAPFIND_TOTAL_CHUNKS"] = "1"
                log_path = work / "seat_extractor.log"
                with log_path.open("w", encoding="utf-8") as log:
                    p = subprocess.Popen(
                        [sys.executable, str(SCRIPTS / "seat_matrix_extractor.py"),
                         str(pdf_path), "--out", str(raw), "--dpi", "200", "--no-json"],
                        cwd=str(BASE), stdout=log, stderr=subprocess.STDOUT, text=True, env=env,
                    )
                    started = time.monotonic()
                    while p.poll() is None:
                        if _cancel_requested(job_id):
                            p.terminate()
                            try:
                                p.wait(timeout=8)
                            except subprocess.TimeoutExpired:
                                p.kill()
                                p.wait(timeout=3)
                            _raise_if_cancelled(conn, job_id)
                        # Large CAP seat-matrix PDFs can legitimately take longer than
                        # 30 minutes, especially when OCR is needed. Scale the watchdog
                        # from the document length instead of killing a healthy long job.
                        if time.monotonic() - started > timeout_seconds:
                            p.kill()
                            p.wait(timeout=5)
                            raise RuntimeError(
                                f"Seat-matrix extractor timed out after {int(timeout_seconds // 60)} minutes "
                                f"for a {expected_pages}-page PDF"
                            )
                        time.sleep(0.25)
                extractor_output = log_path.read_text(encoding="utf-8", errors="replace")
                _raise_if_cancelled(conn, job_id)
                if p.returncode != 0:
                    raise RuntimeError("Seat-matrix extractor failed: " + extractor_output[-6000:])
                summary = {}
                # CLI prints a final JSON summary. Parse the last JSON object rather
                # than depending on incidental progress output.
                for line in reversed([x.strip() for x in extractor_output.splitlines()]):
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            summary = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            pass
                extracted_path = raw / f"{pdf_path.stem}_seats_long.csv"
                if not extracted_path.exists():
                    raise RuntimeError("Seat extractor produced no long-seat CSV artifact")
            canonical = normalized / _canonical_seat_name(family)

            shutil.copy2(extracted_path, canonical)
            event(conn, job_id, "EXTRACT", f"Extracted {summary.get('seat_rows_extracted', 0)} seat rows", 60)
            update_status(conn, job_id, JobStatus.NORMALIZING.value, "Canonicalizing seat-matrix artifact")
            event(conn, job_id, "NORMALIZE", f"Normalized artifact: {canonical.name}", 68)
            update_status(conn, job_id, JobStatus.VALIDATING.value, "Running seat-matrix data quality gate")
            event(conn, job_id, "VALIDATE", "Running existing validate_seats.py gate", 78)
            valid, validation = _run_validator(SCRIPTS / "validate_seats.py", normalized)
            (work / "validation.txt").write_text(validation, encoding="utf-8")
            rows, row_quarantine = _stage_csv(
                conn, job_id, "SEATS", canonical, valid, validation,
                ("institution_code", "choice_code", "allocation_type", "category", "seats"),
                progress_callback=progress_callback,
                expected_rows=summary.get("seat_rows_extracted"),
            )
            valid = valid and row_quarantine == 0
            shutil.copy2(canonical, staging / canonical.name)
            shutil.copy2(work / "validation.txt", staging / "validation.txt")
            _insert_result(conn, job_id, "SEATS", extracted_path, canonical,
                           valid, int(summary.get("seat_rows_extracted", rows)), rows - row_quarantine, row_quarantine,
                           {"extractor": summary, "validation": validation[-12000:]})

        _raise_if_cancelled(conn, job_id)
        update_status(conn, job_id, JobStatus.COMPARING.value, "Comparing staged rows with existing production data")
        result_row = conn.execute("SELECT * FROM import_results WHERE job_id=? ORDER BY id DESC LIMIT 1", (job_id,)).fetchone()
        if result_row and result_row["result_type"] == "CUTOFFS":
            comparison = _compare_cutoffs(conn, canonical, family, year, round_name)
        else:
            comparison = _compare_seats(conn, canonical, family, year)
        conn.execute("UPDATE import_results SET summary_json=? WHERE id=?",
                     (json.dumps({**json.loads(result_row["summary_json"] or "{}"), "comparison": comparison}, ensure_ascii=False),
                      result_row["id"]))
        event(conn, job_id, "COMPARE",
              f"Compared {comparison.get('rows_compared', 0)} staged rows; "
              f"{comparison.get('already_present_exact_key', 0)} exact keys already exist",
              88)
        update_status(conn, job_id, JobStatus.STAGED.value, "Extraction, normalization and validation artifacts staged")
        event(conn, job_id, "STAGED", "No production fact rows were modified", 100)
        result_row = conn.execute(
            "SELECT validation_status FROM import_results WHERE job_id=? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if result_row and result_row["validation_status"] == "PASS":
            update_status(conn, job_id, JobStatus.STAGED.value, "Validation passed; ready for production approval")
            event(conn, job_id, "READY", "Validation passed; no review is required", 100)
            final_status = JobStatus.STAGED.value
        else:
            update_status(conn, job_id, JobStatus.REVIEW_REQUIRED.value, "Validation findings require admin review")
            event(conn, job_id, "REVIEW", "Validation findings require Review Center attention", 100)
            final_status = JobStatus.REVIEW_REQUIRED.value
        _raise_if_cancelled(conn, job_id)
        conn.commit()
        return {"ok": True, "job_id": job_id, "status": final_status,
                "work_dir": str(work.relative_to(BASE))}
    except ImportCancelled:
        conn.rollback()
        marker = _cancel_marker(job_id)
        if marker.exists():
            marker.unlink()
        return {"ok": True, "job_id": job_id, "status": JobStatus.CANCELLED.value, "cancelled": True}
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE import_jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (JobStatus.FAILED.value, str(exc), job_id))
        event(conn, job_id, "ERROR", str(exc), None)
        conn.commit()
        return {"ok": False, "job_id": job_id, "status": JobStatus.FAILED.value, "error": str(exc)}


def _load_staged_rows(conn, job_id: int, result_type: str):
    rows = conn.execute(
        "SELECT id, COALESCE(normalized_json,raw_json) AS normalized_json, validation_status FROM import_staging_records "
        "WHERE job_id=? AND result_type=? ORDER BY id", (job_id, result_type)
    ).fetchall()
    return rows


def _iter_staged_rows(conn, job_id: int, result_type: str, batch_size: int = 200):
    """Yield staged rows in keyset batches instead of retaining an import in RAM."""
    batch_size = max(1, int(batch_size))
    last_id = 0
    while True:
        rows = conn.execute(
            """SELECT id, COALESCE(normalized_json,raw_json) AS normalized_json, validation_status
               FROM import_staging_records
               WHERE job_id=? AND result_type=? AND id>?
               ORDER BY id LIMIT ?""",
            (job_id, result_type, last_id, batch_size),
        ).fetchall()
        if not rows:
            return
        last_id = int(rows[-1]["id"])
        yield from rows


def _iter_release_items(conn, release_id: int, *, newest_first: bool = False,
                        batch_size: int = 500):
    """Page rollback ledger rows so a large release does not load its ledger into RAM."""
    batch_size = max(1, int(batch_size))
    last_id = 9223372036854775807 if newest_first else 0
    while True:
        if newest_first:
            rows = conn.execute(
                "SELECT * FROM data_release_items WHERE release_id=? AND id<? ORDER BY id DESC LIMIT ?",
                (release_id, last_id, batch_size),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM data_release_items WHERE release_id=? AND id>? ORDER BY id LIMIT ?",
                (release_id, last_id, batch_size),
            ).fetchall()
        if not rows:
            return
        last_id = int(rows[-1]["id"])
        yield from rows


def _require_clean_stage(conn, job_id: int, result_type: str):
    result = conn.execute(
        "SELECT * FROM import_results WHERE job_id=? AND result_type=? ORDER BY id DESC LIMIT 1",
        (job_id, result_type)
    ).fetchone()
    if not result:
        raise ValueError("No staged result exists for this import")
    if result["validation_status"] != "PASS":
        raise ValueError("Import has validation findings and cannot be approved automatically")
    bad = conn.execute(
        "SELECT COUNT(*) AS n FROM import_staging_records "
        "WHERE job_id=? AND result_type=? AND validation_status!='VALID'",
        (job_id, result_type)
    ).fetchone()["n"]
    if bad:
        raise ValueError(f"{bad} staged rows are not VALID; resolve them before approval")
    return result



def revalidate_legacy_mh_staging(conn, job_id: int, actor_user_id: int):
    """Repair only the known legacy BCA 2026 CAP-2 MH validator mismatch.

    The source PDF can be unavailable on ephemeral hosting, so this path
    revalidates the already-staged rows against current canonical rules. It is
    intentionally restricted to one known filename and the exact historical
    validator signature; it never commits production data.
    """
    import re
    import csv

    job = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        raise ValueError("Import not found")
    if (
        job.get("original_filename") != "2026BCA_CAP2_MH_CutOff.pdf"
        or str(job.get("course_family") or "").upper() != "BCA"
        or int(job.get("year") or 0) != 2026
        or str(job.get("round") or "").upper() not in {"C2", "2", "ROUND 2"}
        or job.get("data_type") != "CUTOFFS"
    ):
        raise ValueError("This repair is restricted to the known 2026 BCA CAP-2 MH import")
    if job.get("status") != JobStatus.REVIEW_REQUIRED.value:
        raise ValueError(f"Import is not awaiting review: {job.get('status')}")

    result = conn.execute(
        "SELECT * FROM import_results WHERE job_id=? AND result_type='CUTOFFS' ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if not result or result.get("validation_status") != "REVIEW_REQUIRED":
        raise ValueError("The expected legacy validation result was not found")
    try:
        summary = json.loads(result.get("summary_json") or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Stored validation summary is unreadable") from exc
    report = str(summary.get("validation") or "")

    # Do not waive any issue other than the four obsolete MH category reports.
    required_report_checks = (
        re.search(r"Total issues:\s*4\b", report),
        re.search(r"=== UNKNOWN CATEGORIES \(1\) ===", report),
        re.search(r"^\s*\[MH\]\s*:\s*4\s*$", report, re.MULTILINE),
        re.search(r"=== UNKNOWN STAGES \(0\) ===", report),
        re.search(r"=== UNKNOWN SECTIONS \(0\) ===", report),
        re.search(r"=== UNKNOWN PROGRAM NAMES \(0\) ===", report),
        re.search(r"Exact duplicate rows detected:\s*0\b", report),
    )
    if not all(required_report_checks) or "=== FILE ERRORS ===" in report:
        raise ValueError("Stored report does not match the narrowly approved MH-only legacy issue; no changes made")

    alias_path = BASE / "data" / "reference" / "program_aliases.csv"
    with alias_path.open("r", encoding="utf-8-sig", newline="") as handle:
        valid_programs = {str(row.get("raw_name", "")).strip() for row in csv.DictReader(handle)}
    rows = conn.execute(
        "SELECT id,result_type,COALESCE(normalized_json,raw_json) AS normalized_json,validation_status FROM import_staging_records WHERE job_id=? ORDER BY id",
        (job_id,),
    ).fetchall()
    if len(rows) != 327 or any(row.get("result_type") != "CUTOFFS" for row in rows):
        raise ValueError(f"Expected exactly 327 cutoff staging rows; found {len(rows)}. No changes made")

    # Validate every staged row before changing any record.
    repaired_ids = []
    for row in rows:
        try:
            normalized = json.loads(row.get("normalized_json") or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Staged row {row['id']} contains invalid JSON; no changes made") from exc
        for field in ("institution_code", "program_name", "category", "percentage"):
            if not str(normalized.get(field, "")).strip():
                raise ValueError(f"Staged row {row['id']} is missing {field}; no changes made")
        if str(normalized.get("program_name", "")).strip() not in valid_programs:
            raise ValueError(f"Staged row {row['id']} has an unrecognized program; no changes made")
        try:
            _resolve_cutoff_dimensions(normalized)
            float(normalized["percentage"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Staged row {row['id']} still fails current validation: {exc}; no changes made") from exc
        repaired_ids.append(int(row["id"]))

    # All checks passed: repair staging metadata only. Production remains untouched.
    for row_id in repaired_ids:
        conn.execute(
            "UPDATE import_staging_records SET validation_status='VALID',validation_message=NULL WHERE id=? AND job_id=?",
            (row_id, job_id),
        )
    summary["legacy_revalidation"] = {
        "rule": "MH -> MI canonical category mapping",
        "reason": "Historical validator flagged four MH labels that current canonical parsing accepts as MI",
        "rows_revalidated": len(repaired_ids),
        "source_pdf_reextracted": False,
        "production_committed": False,
    }
    conn.execute(
        "UPDATE import_results SET validation_status='PASS',rows_validated=?,summary_json=? WHERE id=?",
        (len(repaired_ids), json.dumps(summary, ensure_ascii=False), result["id"]),
    )
    event(conn, job_id, "LEGACY_REVALIDATION",
          f"Revalidated {len(repaired_ids)} existing cutoff rows against current rules; no production changes made", 100)
    conn.execute(
        """INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,before_json,after_json,reason)
           VALUES (?,?,?,?,?,?,?)""",
        (actor_user_id, "REVALIDATE_STAGED_IMPORT", "IMPORT", str(job_id),
         json.dumps({"validation_status": result["validation_status"]}),
         json.dumps({"validation_status": "PASS", "rows_revalidated": len(repaired_ids)}),
         "Narrow MH-to-MI legacy validation repair; original PDF was not re-extracted"),
    )
    conn.commit()
    return {"ok": True, "job_id": job_id, "rows_revalidated": len(repaired_ids),
            "status": JobStatus.REVIEW_REQUIRED.value, "production_committed": False}

@lru_cache(maxsize=1)
def _cutoff_program_levels():
    """Read program aliases once; never rebuild a pandas DataFrame per row."""
    path = BASE / "data" / "reference" / "program_aliases.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("raw_name", "")).strip(): str(row.get("level", "")).strip()
            for row in csv.DictReader(handle)
        }


@lru_cache(maxsize=1)
def _seat_import_whitelists():
    from scripts.validate_seats import load_whitelists
    return load_whitelists(BASE / "data" / "reference")


def _insert_cutoff_from_json(conn, raw, job, source_pdf, reference_cache=None):
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from validate_data import parse_filename
    family = job["course_family"]
    reference_cache = reference_cache if reference_cache is not None else {
        "institutes": set(), "base_categories": set(), "sections": set(), "stages": set(), "program_ids": {}
    }
    program_name = str(raw.get("program_name","")).strip()
    inst = str(raw.get("institution_code","")).strip()
    if not program_name or not inst:
        raise ValueError("Missing institution_code/program_name after normalization")
    base, ladies, section, stage = _resolve_cutoff_dimensions(raw)
    pct = float(raw["percentage"])
    rank = str(raw.get("rank_number","")).strip()
    rank_number = int(rank) if rank.isdigit() else None
    suffix = str(raw.get("rank_suffix","")).strip() or None

    level = _cutoff_program_levels().get(program_name)
    # A PDF can legitimately contain an institute that is not yet present in
    # the reference table. The PDF is the authoritative source for its code
    # and name at import time; upsert that reference row before the fact row
    # so PostgreSQL's FK remains enforced without requiring a manual seed run.
    if inst not in reference_cache["institutes"]:
        conn.execute("""INSERT INTO institutes(institution_code,institution_name)
            VALUES(?,?) ON CONFLICT(institution_code) DO UPDATE SET institution_name=EXCLUDED.institution_name""",
            (inst, str(raw.get("institution_name","")).strip() or inst))
        reference_cache["institutes"].add(inst)
    if base not in reference_cache["base_categories"]:
        conn.execute("INSERT INTO base_categories(base_code) VALUES(?) ON CONFLICT(base_code) DO NOTHING", (base,))
        reference_cache["base_categories"].add(base)
    if section not in reference_cache["sections"]:
        conn.execute("INSERT INTO sections(section_code,section_full) VALUES(?,?) ON CONFLICT(section_code) DO NOTHING",
                     (section, section))
        reference_cache["sections"].add(section)
    if stage not in reference_cache["stages"]:
        conn.execute("INSERT INTO stages(stage_code) VALUES(?) ON CONFLICT(stage_code) DO NOTHING", (stage,))
        reference_cache["stages"].add(stage)
    program_key = (family, program_name)
    if program_key not in reference_cache["program_ids"]:
        conn.execute("INSERT INTO programs(program_family,program_name_raw,level) VALUES(?,?,?) ON CONFLICT(program_family,program_name_raw) DO NOTHING",
                     (family,program_name,level))
        prog=conn.execute("SELECT program_id FROM programs WHERE program_family=? AND program_name_raw=?",
                          (family,program_name)).fetchone()
        if not prog: raise ValueError(f"Unable to resolve program: {program_name}")
        reference_cache["program_ids"][program_key] = prog["program_id"]
    pid=reference_cache["program_ids"][program_key]
    program_code=str(raw.get("program_code", "")).strip() or None
    vals=(int(job["year"]),int(str(job["round"])[1:]),inst,pid,program_code,base,bool(ladies),
          section,stage,None,rank_number,suffix,pct,str(raw.get("category","")).strip(),
          program_name,source_pdf,int(raw["page"]) if str(raw.get("page","")).isdigit() else None)
    cur=conn.execute("""INSERT INTO cutoffs
        (year,round,institution_code,program_id,program_code,base_category,is_ladies,section_code,
         stage_code,home_university,rank_number,rank_suffix,percentile,raw_category,
         raw_program_name,source_pdf,source_page)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING id""", vals)
    inserted=cur.fetchone()
    if inserted:
        rid=inserted["id"]
        after=dict(zip(["year","round","institution_code","program_id","program_code","base_category","is_ladies",
                        "section_code","stage_code","home_university","rank_number","rank_suffix",
                        "percentile","raw_category","raw_program_name","source_pdf","source_page"], vals))
        return rid, after
    return None, None


def _insert_seat_from_json(conn, raw, job, source_pdf, reference_cache=None):
    from scripts.ingest_seats import canonical_institution_code
    from scripts.validate_seats import normalize_category, TOTAL_MARKER
    reference_cache = reference_cache if reference_cache is not None else {
        "institutes": set(), "base_categories": set(), "allocation_lanes": set()
    }
    _valid_cats, lane_map, alias_map = _seat_import_whitelists()
    inst=canonical_institution_code(str(raw.get("institution_code","")),str(raw.get("choice_code","")))
    lane_raw=str(raw.get("allocation_type","")).strip()
    lane=lane_map.get(lane_raw)
    if not lane: raise ValueError(f"Unknown allocation type: {lane_raw!r}")
    # The standalone seat ingester bootstraps allocation_lanes before inserts,
    # but the admin import path writes directly to the production connection.
    # Ensure the referenced lane exists here as well so a fresh Render database
    # cannot reject an otherwise validated seat row with a foreign-key error.
    if lane not in reference_cache["allocation_lanes"]:
        conn.execute(
            "INSERT INTO allocation_lanes(lane_code,lane_full) VALUES(?,?) ON CONFLICT(lane_code) DO NOTHING",
            (lane, lane_raw),
        )
        reference_cache["allocation_lanes"].add(lane)
    cat=str(raw.get("category","")).strip()
    total=cat.casefold()==TOTAL_MARKER.casefold()
    base=None if total else normalize_category(cat,alias_map)
    from scripts.category_codes import is_category_code
    if not total and not is_category_code(cat): raise ValueError(f"Malformed category code: {cat!r}")

    # Seat imports use the same PostgreSQL FK graph as cutoff imports.
    # The standalone seat ingester seeds these reference rows, but the admin
    # approval path writes directly to production and must do the same.
    if inst not in reference_cache["institutes"]:
        conn.execute(
            "INSERT INTO institutes(institution_code,institution_name) VALUES(?,?) "
            "ON CONFLICT(institution_code) DO UPDATE SET institution_name=EXCLUDED.institution_name",
            (inst, str(raw.get("institution_name","")).strip() or inst),
        )
        reference_cache["institutes"].add(inst)
    if base is not None and base not in reference_cache["base_categories"]:
        conn.execute(
            "INSERT INTO base_categories(base_code) VALUES(?) ON CONFLICT(base_code) DO NOTHING",
            (base,),
        )
        reference_cache["base_categories"].add(base)
    gender=str(raw.get("gender","")).strip()
    is_ladies={"G":False,"L":True}.get(gender) if gender else None
    source_row = int(raw["source_row"]) if str(raw.get("source_row", "")).isdigit() else None
    vals=(int(job["year"]),job["course_family"],inst,str(raw.get("choice_code","")).strip(),
          lane,base,total,is_ladies,int(raw["seats"]),cat,lane_raw,gender,
          source_pdf,int(raw["page"]) if str(raw.get("page","")).isdigit() else None,
          source_row)
    cur=conn.execute("""INSERT INTO seats
        (capture_year,program_family,institution_code,choice_code,allocation_lane,base_category,
         is_total,is_ladies,seats,raw_category,raw_allocation_type,raw_gender,source_pdf,source_page,source_row)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT DO NOTHING RETURNING id""", vals)
    inserted=cur.fetchone()
    if inserted:
        rid=inserted["id"]
        cols=["capture_year","program_family","institution_code","choice_code","allocation_lane",
              "base_category","is_total","is_ladies","seats","raw_category","raw_allocation_type",
              "raw_gender","source_pdf","source_page","source_row"]
        return rid, dict(zip(cols,vals))
    return None,None



def _insert_seat_course_metadata(conn, raw, job, source_pdf):
    """Persist one official course/choice-code summary from the source PDF."""
    metadata = raw.get("course_metadata")
    if not metadata:
        return False
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid course_metadata JSON: {exc}")
    if not isinstance(metadata, dict):
        raise ValueError("course_metadata must be a JSON object")
    from scripts.ingest_seats import canonical_institution_code
    institution = canonical_institution_code(
        str(raw.get("institution_code", "")), str(raw.get("choice_code", ""))
    )
    choice = str(raw.get("choice_code", "")).strip()
    if not institution or not choice:
        raise ValueError("Seat-matrix course metadata has no institution/choice code")
    metadata_pdf = str(metadata.get("source_pdf") or raw.get("source_pdf") or source_pdf)
    page = metadata.get("page") or raw.get("page")
    page = int(page) if str(page or "").isdigit() else None
    conn.execute("""INSERT INTO seat_matrix_courses
        (capture_year,program_family,institution_code,choice_code,source_pdf,source_page,source_job_id,course_metadata)
        VALUES (?,?,?,?,?,?,?,CAST(? AS jsonb))
        ON CONFLICT(capture_year,program_family,institution_code,choice_code) DO NOTHING""",
        (int(job["year"]), job["course_family"], institution, choice,
         metadata_pdf, page, int(job["id"]), json.dumps(metadata, ensure_ascii=False)))
    return True


def _write_commit_progress(job_id: int, status: str, stage: str,
                           processed: int, total: int, message: str) -> None:
    """Persist progress outside the production-row transaction so polling can see it live."""
    total = max(0, int(total))
    processed = max(0, min(int(processed), total)) if total else 0
    progress = 100 if status == "COMPLETED" else (min(99, int(processed * 100 / total)) if total else 0)
    with connect() as progress_conn:
        progress_conn.execute(
            """INSERT INTO import_commit_progress
               (job_id,status,stage,processed,total,progress,message,updated_at)
               VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(job_id) DO UPDATE SET
                 status=EXCLUDED.status, stage=EXCLUDED.stage,
                 processed=EXCLUDED.processed, total=EXCLUDED.total,
                 progress=EXCLUDED.progress, message=EXCLUDED.message,
                 updated_at=CURRENT_TIMESTAMP""",
            (job_id, status, stage, processed, total, progress, message),
        )
        progress_conn.commit()


def _rollback_metadata(after: dict) -> dict:
    """Project a fact row to the only fields rollback needs for reference cleanup."""
    return {key: after[key] for key in ("institution_code", "program_id") if key in after}


def _insert_release_items_batched(conn, release_id: int, inserted: list[tuple], batch_size: int = 500) -> None:
    """Write release history in bounded batches without changing its contents."""
    for start in range(0, len(inserted), batch_size):
        batch = inserted[start:start + batch_size]
        payload = json.dumps([
            {
                "table_name": table,
                "row_id": int(row_id),
                "operation": "INSERT",
                "before_json": None,
                # Rollback needs only the owning institution and (for cutoffs)
                # program to clean up orphaned reference rows. The full values
                # remain in authoritative fact rows and source staging.
                "after_json": json.dumps(_rollback_metadata(after), ensure_ascii=False),
            }
            for table, row_id, after in batch
        ], ensure_ascii=False)
        result = conn.execute(
            """INSERT INTO data_release_items
               (release_id,table_name,row_id,operation,before_json,after_json)
               SELECT ?, item.table_name, item.row_id, item.operation,
                      item.before_json, item.after_json
               FROM jsonb_to_recordset(?) AS item(
                   table_name TEXT, row_id INTEGER, operation TEXT,
                   before_json TEXT, after_json TEXT
               ) RETURNING id""",
            (release_id, payload),
        )
        # Connection.execute consumes the first RETURNING row to preserve its
        # single-insert lastrowid behavior; drain the rest of this bounded batch.
        result.fetchall()

def approve_import(conn, job_id: int, actor_user_id: int, notes: str = ""):
    """Atomically promote a clean staged import into production and create a release."""
    job=conn.execute("SELECT * FROM import_jobs WHERE id=?",(job_id,)).fetchone()
    if not job: raise ValueError("Import not found")
    if job["status"] not in {JobStatus.STAGED.value, JobStatus.REVIEW_REQUIRED.value}:
        raise ValueError(f"Import is not awaiting approval: {job['status']}")
    dtype=job["data_type"]
    _require_clean_stage(conn,job_id,dtype)
    total_rows = int(conn.execute(
        "SELECT COUNT(*) AS n FROM import_staging_records WHERE job_id=?",
        (job_id,),
    ).fetchone()["n"])
    _write_commit_progress(job_id, "RUNNING", "Preparing transaction", 0, total_rows,
                           "Validation passed; preparing the atomic database commit")
    conn.execute("BEGIN IMMEDIATE")
    try:
        update_status(conn,job_id,JobStatus.APPROVED.value,"Approved by admin; beginning transactional production commit")
        event(conn,job_id,"APPROVAL","Production promotion approved",None)
        update_status(conn,job_id,JobStatus.COMMITTING.value,"Promoting staged rows into production")
        source_pdf=job["original_filename"]
        release_key=f"REL-{job['job_key']}"
        release_result = conn.execute("""INSERT INTO data_releases
            (release_key,source_job_id,source_sha256,status,approved_by,notes)
            VALUES (?,?,?,?,?,?) RETURNING id""",
            (release_key,job_id,job["sha256"],"COMMITTED",actor_user_id,notes))
        release_row = release_result.fetchone()
        if not release_row:
            raise RuntimeError("Unable to resolve newly created release id")
        release_id=release_row["id"]

        # The complete staged import and release history used to be held in two
        # Python lists until the transaction finished. Large PDFs could therefore
        # exhaust the web process's memory during commit. Keyset-page the staging
        # rows and flush each bounded release batch inside the same transaction.
        inserted_batch=[]
        inserted_count=0
        # Progress is persisted on a separate connection so the UI can poll
        # during the atomic transaction. Keep it useful without making every
        # percentage point an extra database transaction.
        progress_interval = max(100, (total_rows + 19) // 20) if total_rows else 1
        processed_rows = 0
        seat_metadata_written = set()
        reference_cache = ({"institutes": set(), "base_categories": set(), "sections": set(), "stages": set(), "program_ids": {}}
                           if dtype == "CUTOFFS" else
                           {"institutes": set(), "base_categories": set(), "allocation_lanes": set()})
        _write_commit_progress(job_id, "RUNNING", "Writing production records", 0, total_rows,
                               f"Writing 0 of {total_rows:,} staged records")
        for r in _iter_staged_rows(conn,job_id,dtype):
            raw=json.loads(r["normalized_json"])
            if dtype=="CUTOFFS":
                rid, after=_insert_cutoff_from_json(conn,raw,job,source_pdf,reference_cache)
                table="cutoffs"
            else:
                rid, after=_insert_seat_from_json(conn,raw,job,source_pdf,reference_cache)
                table="seats"
                metadata = raw.get("course_metadata")
                if metadata:
                    metadata_key = (str(raw.get("institution_code", "")).strip(),
                                    str(raw.get("choice_code", "")).strip())
                    if metadata_key not in seat_metadata_written:
                        _insert_seat_course_metadata(conn, raw, job, source_pdf)
                        seat_metadata_written.add(metadata_key)
            if rid is not None:
                inserted_batch.append((table,rid,after))
                inserted_count += 1
                if len(inserted_batch) >= 200:
                    _insert_release_items_batched(conn, release_id, inserted_batch)
                    inserted_batch.clear()
            processed_rows += 1
            if processed_rows % progress_interval == 0 or processed_rows == total_rows:
                _write_commit_progress(
                    job_id, "RUNNING", "Writing production records", processed_rows, total_rows,
                    f"Processed {processed_rows:,} of {total_rows:,} staged records",
                )
        _write_commit_progress(job_id, "RUNNING", "Creating release", total_rows, total_rows,
                               f"All {total_rows:,} staged records processed; creating release and audit entries")
        if inserted_batch:
            _insert_release_items_batched(conn, release_id, inserted_batch)
            inserted_batch.clear()
        event(conn,job_id,"COMMIT",f"Committed {inserted_count} new production rows",90)
        update_status(conn,job_id,JobStatus.COMMITTING.value,"Production commit completed; release created; publishing is the next phase")
        event(conn,job_id,"RELEASE",f"Release {release_key} committed",100)
        conn.execute("""INSERT INTO audit_log
            (actor_user_id,action,entity_type,entity_id,before_json,after_json,reason)
            VALUES (?,?,?,?,?,?,?)""",
            (actor_user_id,"APPROVE_IMPORT","IMPORT",str(job_id),None,
             json.dumps({"release_id":release_id,"release_key":release_key,
                         "rows_inserted":inserted_count},ensure_ascii=False),notes or "Approved import"))
        conn.commit()
        _write_commit_progress(job_id, "COMPLETED", "Database commit complete", total_rows, total_rows,
                f"Database commit complete: {inserted_count:,} new rows saved. Release {release_key} is awaiting publish.")
        return {"ok":True,"job_id":job_id,"status":"COMMITTING","release_key":release_key,
                "release_id":release_id,"rows_inserted":inserted_count}
    except Exception as exc:
        conn.rollback()
        try:
            _write_commit_progress(job_id, "FAILED", "Commit failed", 0, total_rows,
                                   "Transaction rolled back: " + str(exc)[:500])
        except Exception:
            pass
        # Preserve a durable failure state in a separate transaction.
        conn.execute("UPDATE import_jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (JobStatus.FAILED.value,"Production commit failed; transaction rolled back",job_id))
        conn.execute("INSERT INTO import_events(job_id,event_type,message,progress) VALUES (?,?,?,?)",
                     (job_id,"ERROR","Production commit failed; transaction rolled back",None))
        conn.commit()
        raise


def purge_rolled_back_release(conn, release_id: int, actor_user_id: int):
    """Permanently remove a rolled-back release and its source import artifacts."""
    release=conn.execute("SELECT * FROM data_releases WHERE id=?",(release_id,)).fetchone()
    if not release: raise ValueError("Release not found")
    if release["status"] != "ROLLED_BACK":
        raise ValueError("Only a rolled-back release can be permanently deleted")
    job_id=release["source_job_id"]
    job=conn.execute("SELECT * FROM import_jobs WHERE id=?",(job_id,)).fetchone() if job_id else None
    affected_institutes=set(); affected_program_ids=set()
    for item in _iter_release_items(conn, release_id):
        try: after=json.loads(item["after_json"] or "{}")
        except Exception: after={}
        code=str(after.get("institution_code","")).strip()
        if code: affected_institutes.add(code)
        pid=after.get("program_id")
        if pid is not None:
            try: affected_program_ids.add(int(pid))
            except (TypeError,ValueError): pass
    # The caller's connection already has an active SQLAlchemy transaction from
    # the reads above; do not issue a nested BEGIN here.
    try:
        conn.execute("DELETE FROM data_release_items WHERE release_id=?",(release_id,))
        if job_id:
            conn.execute("DELETE FROM seat_matrix_courses WHERE source_job_id=?",(job_id,))
        conn.execute("DELETE FROM data_releases WHERE id=?",(release_id,))
        if job_id:
            conn.execute("DELETE FROM import_events WHERE job_id=?",(job_id,))
            conn.execute("DELETE FROM import_staging_records WHERE job_id=?",(job_id,))
            conn.execute("DELETE FROM import_results WHERE job_id=?",(job_id,))
            conn.execute("DELETE FROM import_jobs WHERE id=?",(job_id,))
        for code in affected_institutes:
            used=conn.execute("SELECT EXISTS(SELECT 1 FROM cutoffs WHERE institution_code=?) OR EXISTS(SELECT 1 FROM seats WHERE institution_code=?) AS used",(code,code)).fetchone()["used"]
            if not used:
                conn.execute("DELETE FROM college_website_resolver WHERE institution_code=?",(code,))
                conn.execute("DELETE FROM institutes WHERE institution_code=?",(code,))
        for pid in affected_program_ids:
            used=conn.execute("SELECT EXISTS(SELECT 1 FROM cutoffs WHERE program_id=?) AS used",(pid,)).fetchone()["used"]
            if not used:
                conn.execute("DELETE FROM programs WHERE program_id=?",(pid,))
        conn.execute("INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,before_json,after_json,reason) VALUES (?,?,?,?,?,?,?)",
                     (actor_user_id,"PURGE_ROLLED_BACK_RELEASE","RELEASE",str(release_id),json.dumps({"release_key":release["release_key"],"source_job_id":job_id}),None,"Permanent deletion of rolled-back release and source import"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if job and job["stored_path"]:
        stored=BASE/job["stored_path"]
        if stored.exists(): stored.unlink()
    if release["backup_path"]:
        backup=BASE/release["backup_path"]
        if backup.exists(): shutil.rmtree(backup,ignore_errors=True)
    for directory in (BASE/'data'/'work'/f"job_{job_id}", BASE/'data'/'staging'/f"job_{job_id}"):
        if directory.exists(): shutil.rmtree(directory,ignore_errors=True)
    return {"ok":True,"release_id":release_id,"status":"DELETED","source_job_id":job_id}


def rollback_release(conn, release_id: int, actor_user_id: int, reason: str):
    release=conn.execute("SELECT * FROM data_releases WHERE id=?",(release_id,)).fetchone()
    if not release: raise ValueError("Release not found")
    if release["status"] == "ROLLED_BACK": raise ValueError("Release is already rolled back")
    # A published release also has a filesystem backup. Restore that public tree
    # before committing the database rollback, and keep a current-site fallback
    # so a failed DB transaction can restore the public tree too.
    public_root=BASE/'site'; current_backup=None; restored=False
    if release["status"] == "PUBLISHED" and release["backup_path"]:
        backup=BASE/release["backup_path"]
        if not backup.exists(): raise ValueError("Published release backup is missing; refusing rollback")
        current_backup=BASE/'data'/'publish_work'/f'rollback_current_{release_id}_{os.getpid()}_{int(time.time())}'
        current_backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(public_root,current_backup)
        temp=BASE/'data'/'publish_work'/f'rollback_target_{release_id}_{os.getpid()}_{int(time.time())}'
        if temp.exists(): shutil.rmtree(temp)
        shutil.copytree(backup,temp)
        old=BASE/f'.site_rollback_old_{release_id}_{os.getpid()}'
        if old.exists(): shutil.rmtree(old)
        os.replace(public_root,old); os.replace(temp,public_root); shutil.rmtree(old,ignore_errors=True); restored=True
    # The caller's connection already has an active SQLAlchemy transaction.
    try:
        deleted=0
        affected_institutes=set()
        affected_program_ids=set()
        for item in _iter_release_items(conn, release_id, newest_first=True):
            table=item["table_name"]
            if table not in {"cutoffs","seats"}: raise ValueError("Unsupported release table")
            try:
                after=json.loads(item["after_json"] or "{}")
            except Exception:
                after={}
            if table == "cutoffs":
                code=str(after.get("institution_code","")).strip()
                if code: affected_institutes.add(code)
                pid=after.get("program_id")
                if pid is not None:
                    affected_program_ids.add(int(pid))
            elif table == "seats":
                code=str(after.get("institution_code","")).strip()
                if code: affected_institutes.add(code)
            cur=conn.execute(f"DELETE FROM {table} WHERE id=?",(item["row_id"],))
            deleted += cur.rowcount

        # Course metadata is stored once per choice code (rather than repeated
        # for every category row). Remove metadata first introduced by this
        # source job when rolling the release back; older metadata records are
        # retained because the import path does not overwrite them.
        if release["source_job_id"]:
            conn.execute(
                "DELETE FROM seat_matrix_courses WHERE source_job_id=?",
                (release["source_job_id"],),
            )

        # Production reference rows are created as part of imports, but the
        # release ledger historically tracked only cutoff/seat rows. Remove
        # now-orphaned institute/program rows belonging to this release so a
        # rollback really removes the dataset from public/resolver scope.
        orphan_institutes=0
        for code in affected_institutes:
            still_used=conn.execute(
                "SELECT EXISTS(SELECT 1 FROM cutoffs WHERE institution_code=?) "
                "OR EXISTS(SELECT 1 FROM seats WHERE institution_code=?) AS used",
                (code,code),
            ).fetchone()["used"]
            if not still_used:
                conn.execute("DELETE FROM college_website_resolver WHERE institution_code=?",(code,))
                orphan_institutes += conn.execute("DELETE FROM institutes WHERE institution_code=?",(code,)).rowcount

        orphan_programs=0
        for pid in affected_program_ids:
            used=conn.execute("SELECT EXISTS(SELECT 1 FROM cutoffs WHERE program_id=?) AS used",(pid,)).fetchone()["used"]
            if not used:
                orphan_programs += conn.execute("DELETE FROM programs WHERE program_id=?",(pid,)).rowcount

        conn.execute("UPDATE data_releases SET status='ROLLED_BACK',notes=?,backup_path=NULL WHERE id=?",
                     (f"{release['notes'] or ''}\nRollback: {reason}",release_id))
        if release["source_job_id"]:
            update_status(conn,release["source_job_id"],JobStatus.ROLLED_BACK.value,"Release rolled back")
            event(conn,release["source_job_id"],"ROLLBACK",f"Release {release['release_key']} rolled back; deleted {deleted} inserted rows",100)
        conn.execute("""INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,before_json,after_json,reason) VALUES (?,?,?,?,?,?,?)""",
            (actor_user_id,"ROLLBACK_RELEASE","RELEASE",str(release_id),json.dumps({"status":release["status"]}),json.dumps({"status":"ROLLED_BACK","deleted":deleted}),reason))
        conn.commit()
        # The old published-site backup is no longer needed after a successful
        # rollback. Delete it only after the DB transaction commits.
        if release["backup_path"]:
            backup_to_delete=BASE/release["backup_path"]
            if backup_to_delete.exists(): shutil.rmtree(backup_to_delete,ignore_errors=True)
        if current_backup: shutil.rmtree(current_backup,ignore_errors=True)
        return {"ok":True,"release_id":release_id,"deleted":deleted,"status":"ROLLED_BACK"}
    except Exception:
        conn.rollback()
        if restored and current_backup and current_backup.exists():
            temp=BASE/'data'/'publish_work'/f'rollback_recover_{release_id}_{os.getpid()}_{int(time.time())}'
            if temp.exists(): shutil.rmtree(temp)
            shutil.copytree(current_backup,temp)
            old=BASE/f'.site_rollback_recover_old_{release_id}_{os.getpid()}'
            if old.exists(): shutil.rmtree(old)
            os.replace(public_root,old); os.replace(temp,public_root); shutil.rmtree(old,ignore_errors=True)
        raise
