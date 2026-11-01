#!/usr/bin/env python3
"""Run CAPFind's existing PDF extractors over PDFs in local_extraction/input."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "local_extraction" / "input"
OUTPUT = BASE / "local_extraction" / "output"
READY = BASE / "local_extraction" / "ready_to_upload"
REPORTS = BASE / "local_extraction" / "reports"
CHUNK_EXTRACTOR = BASE / "scripts" / "chunked_cutoff_extractor.py"
SEAT_EXTRACTOR = BASE / "scripts" / "seat_matrix_extractor.py"

CUTOFF_VALIDATOR = BASE / "scripts" / "validate_data.py"
SEAT_VALIDATOR = BASE / "scripts" / "validate_seats.py"


def semantic_validate(target: Path, kind: str, source_pdf: Path) -> tuple[int, str]:
    """Run the same strict data-quality gate used before admin publication."""
    with tempfile.TemporaryDirectory(prefix="capfind-semantic-validation-") as tmp:
        folder = Path(tmp)
        if kind == "CUTOFFS":
            stem = source_pdf.stem.upper()
            family = next((f for token, f in (
                ("BCA", "BCA"), ("BBA", "BBA"), ("MBA", "MBA"),
                ("MCA", "MCA"), ("BTECH", "BTECH"),
            ) if token in stem), None)
            if family is None and (
                any(token in stem for token in ("ENGG", "ENGINEERING", "BE_BTECH"))
                or re.search(r"(?:^|[_ -])B\\.?E\\.?(?:[_ -]|$)", stem)
            ):
                family = "BE"
            year_match = re.search(r"(20\d{2})", stem)
            if not year_match:
                year_match = re.search(r"(?:^|_)(\d{2})(?:_|$)", stem)
            round_match = re.search(r"CAP(?:[_ -]?ROUND)?[_ -]*([1-4])", stem)
            if not round_match:
                round_match = re.search(r"(?:^|[_-])C([1-4])(?:[_-]|$)", stem)
            if not family or not year_match or not round_match:
                return 1, (
                    "Strict cutoff validation could not determine course family, year, and CAP round "
                    f"from source filename {source_pdf.name!r}; artifact held for review."
                )
            year_value = int(year_match.group(1))
            year_short = year_value % 100 if year_value >= 2000 else year_value
            canonical_name = f"{family}_{year_short:02d}_C{round_match.group(1)}_cutoffs.csv"
            shutil.copy2(target, folder / canonical_name)
            validator = CUTOFF_VALIDATOR
        else:
            shutil.copy2(target, folder / target.name)
            validator = SEAT_VALIDATOR
        proc = subprocess.run(
            [sys.executable, str(validator), str(folder)],
            cwd=BASE, capture_output=True, text=True, errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output.strip()


def kind_from_name(name: str) -> str | None:
    n = name.lower().replace("-", "_").replace(" ", "_")
    if any(k in n for k in ("seatmatrix", "seat_matrix", "seat_mtx", "_sm", "sm_")):
        return "SEATS"
    if any(k in n for k in ("cutoff", "cut_off", "cap1", "cap2", "cap3", "cap4", "cap_round")):
        return "CUTOFFS"
    return None

def main() -> int:
    ap = argparse.ArgumentParser(description="Extract CAPFind PDFs locally using the existing pipeline.")
    ap.add_argument("--chunk-pages", type=int, default=10, help="Pages per cutoff chunk (default: 10)")
    ap.add_argument("--hybrid", action="store_true", help="Enable OCR fallback in chunked cutoff extraction")
    ap.add_argument("--pdf", action="append", default=[], help="Process only this input PDF filename; may be repeated")
    args = ap.parse_args()
    if not 1 <= args.chunk_pages <= 1000:
        ap.error("--chunk-pages must be between 1 and 1000")
    for folder in (INPUT, OUTPUT, READY, REPORTS):
        folder.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if args.pdf:
        available = {p.name for p in pdfs}
        missing = sorted(set(args.pdf) - available)
        if missing:
            ap.error("Requested PDF(s) not found in input folder: " + ", ".join(missing))
        selected = set(args.pdf)
        pdfs = [p for p in pdfs if p.name in selected]
    if not pdfs:
        print(f"No PDFs found. Copy PDFs into: {INPUT}")
        return 1

    summary = {"started_at": datetime.now().isoformat(timespec="seconds"), "input_folder": str(INPUT),
               "chunk_pages": args.chunk_pages, "files": []}
    failures = 0
    for pdf in pdfs:
        kind = kind_from_name(pdf.name)
        if not kind:
            print(f"SKIP (filename doesn't identify cutoff vs seat matrix): {pdf.name}")
            summary["files"].append({"pdf": pdf.name, "status": "SKIPPED", "error": "Rename file to include cutoff/CAP1-CAP4 or seatmatrix/seat_matrix."})
            failures += 1
            continue
        # Each PDF gets a separate work directory; manifests can never mix source files.
        workdir = OUTPUT / pdf.stem
        manifest_path = workdir / ".chunk_work" / "manifest.json"
        if kind == "CUTOFFS" and manifest_path.is_file():
            try:
                prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                current_source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
                current_chunk_hash = hashlib.sha256(CHUNK_EXTRACTOR.read_bytes()).hexdigest()
                current_page_hash = hashlib.sha256((BASE / "scripts" / "cutoff_extractor.py").read_bytes()).hexdigest()
                expected_engine = "hybrid" if args.hybrid else "native_only"
                stale = any((
                    prior_manifest.get("source_sha256") != current_source_hash,
                    prior_manifest.get("chunk_pages") != args.chunk_pages,
                    prior_manifest.get("engine") != expected_engine,
                    prior_manifest.get("chunked_extractor_sha256") != current_chunk_hash,
                    prior_manifest.get("page_extractor_sha256") != current_page_hash,
                ))
                if stale:
                    archive = OUTPUT / f"{pdf.stem}_stale_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.move(str(workdir), str(archive))
                    print(f"Archived stale extraction workdir to: {archive}", flush=True)
            except (OSError, ValueError, TypeError) as exc:
                raise RuntimeError(f"Cannot safely resume prior extraction in {workdir}: {exc}") from exc
        workdir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== {kind}: {pdf.name} ===", flush=True)
        if kind == "CUTOFFS":
            cmd = [sys.executable, str(CHUNK_EXTRACTOR), str(pdf), "--out", str(workdir),
                   "--chunk-pages", str(args.chunk_pages), "--source-name", pdf.name]
            if args.hybrid:
                cmd.append("--hybrid")
        else:
            cmd = [sys.executable, str(SEAT_EXTRACTOR), str(pdf), "--out", str(workdir), "--no-json"]
        log_path = REPORTS / f"{pdf.stem}.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace", bufsize=1)
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return_code = proc.wait()
        if return_code != 0:
            print(f"FAILED: {pdf.name}; see {log_path}", file=sys.stderr)
            summary["files"].append({"pdf": pdf.name, "kind": kind, "status": "FAILED",
                                     "return_code": return_code, "log": str(log_path)})
            failures += 1
            continue
        suffix = "_cutoffs.csv" if kind == "CUTOFFS" else "_seats_long.csv"
        candidates = sorted(workdir.rglob(f"*{suffix}"))
        candidates = [p for p in candidates if p.name != "ALL_PDFS_cutoffs.csv"]
        if not candidates:
            summary["files"].append({"pdf": pdf.name, "kind": kind, "status": "FAILED",
                                     "error": f"Extractor exited successfully but no {suffix} was found", "log": str(log_path)})
            failures += 1
            continue
        # The chunked cutoff extractor's final canonical artifact is at the workdir root.
        artifact = next((p for p in candidates if p.parent == workdir), candidates[-1])
        target = READY / f"{pdf.stem}{suffix}"
        shutil.copy2(artifact, target)
        # Semantic QA runs before an artifact can enter ready_to_upload.
        # Never discard malformed rows or silently repair program identity.
        import csv
        with target.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = set(reader.fieldnames or [])
            data_rows = list(reader)
        first_row = bool(data_rows)
        header = ",".join(reader.fieldnames or [])
        required = ({"source_pdf", "page", "institution_code", "institution_name", "program_code",
                     "program_name", "status", "home_university", "section", "stage", "category",
                     "rank", "rank_number", "rank_suffix", "percentage", "percentage_raw", "raw_value",
                     "source", "merged_from"} if kind == "CUTOFFS" else
                    {"source_pdf", "page", "institution_code", "choice_code", "allocation_type",
                     "category", "gender", "seats"})
        cols = {x.strip().lstrip("\ufeff") for x in columns}
        missing = sorted(required - cols)
        errors = []
        if not first_row: errors.append("CSV contains no data rows")
        if missing: errors.append("missing canonical columns: " + ", ".join(missing))
        if kind == "CUTOFFS":
            for i, row in enumerate(data_rows, 2):
                for field in ("source_pdf", "page", "institution_code", "institution_name", "program_code", "program_name", "category", "rank", "percentage"):
                    if not str(row.get(field, "")).strip():
                        errors.append(f"row {i}: required field {field!r} is blank")
                        if len(errors) >= 50: break
                try:
                    page_num = int(row.get("page", ""))
                    pct = float(row.get("percentage", ""))
                    rank_num = int(row.get("rank_number", ""))
                    if page_num < 1: raise ValueError("page must be >= 1")
                    if not 0 <= pct <= 100: raise ValueError("percentile outside 0..100")
                    if rank_num < 0: raise ValueError("rank must be non-negative")
                except (TypeError, ValueError) as exc:
                    errors.append(f"row {i}: invalid page/rank/percentage ({exc})")
                if len(errors) >= 50: break
            # One institution + official program code must always resolve to
            # one complete source program name; this catches wrapped-title
            # truncation and accidental branch metadata bleed.
            program_names_by_key = {}
            for row_num, row in enumerate(data_rows, 2):
                key = (str(row.get("institution_code", "")).strip(),
                       str(row.get("program_code", "")).strip())
                name = str(row.get("program_name", "")).strip()
                if not all(key) or not name:
                    continue
                prior_name = program_names_by_key.get(key)
                if prior_name is not None and prior_name != name:
                    errors.append(
                        f"rows for institution/program code {key[0]}/{key[1]} disagree on program name: "
                        f"{prior_name!r} vs {name!r} (row {row_num})"
                    )
                    if len(errors) >= 50:
                        break
                else:
                    program_names_by_key[key] = name
            audit_candidates = sorted(workdir.glob("*_page_audit.json"))
            if audit_candidates:
                try:
                    audits = json.loads(audit_candidates[-1].read_text(encoding="utf-8"))
                    page_numbers = [int(a.get("page", 0) or 0) for a in audits]
                    expected_pages = len(page_numbers)
                    manifest_path = workdir / ".chunk_work" / "manifest.json"
                    if manifest_path.is_file():
                        expected_pages = int(json.loads(manifest_path.read_text(encoding="utf-8")).get("total_pages", expected_pages))
                    if sorted(page_numbers) != list(range(1, expected_pages + 1)):
                        errors.append(f"page audit coverage mismatch: expected exactly pages 1..{expected_pages}; found {len(page_numbers)} entries and {len(set(page_numbers))} unique pages")
                    def audited_records(a):
                        fields = ("native_records", "pdfium_records", "ocr_fallback_records", "camelot_records")
                        if any(field in a for field in fields):
                            return sum(int(a.get(field, 0) or 0) for field in fields)
                        return int(a.get("selected_records", 0) or 0)
                    unparsed = [a for a in audits if audited_records(a) == 0 and int(a.get("rank_value_hits", 0) or 0) > 0]
                    if unparsed:
                        errors.append(f"{len(unparsed)} page(s) contain rank/percentile-like source text but produced zero records; first pages: " + ", ".join(str(a.get("page")) for a in unparsed[:10]))
                    empty_pages = [a for a in audits if audited_records(a) == 0]
                    if empty_pages:
                        errors.append(f"{len(empty_pages)} page(s) have zero extracted records and require review; first pages: " + ", ".join(str(a.get("page")) for a in empty_pages[:10]))
                    audited_total = sum(audited_records(a) for a in audits)
                    if audited_total < len(data_rows):
                        errors.append(f"page audit accounts for only {audited_total} records but CSV contains {len(data_rows)} rows")
                    csv_pages = {int(str(r.get("page", "0"))) for r in data_rows if str(r.get("page", "")).isdigit()}
                    missing_csv_pages = sorted(set(range(1, expected_pages + 1)) - csv_pages)
                    if missing_csv_pages:
                        errors.append(f"CSV has no rows from {len(missing_csv_pages)} source page(s); first pages: " + ", ".join(map(str, missing_csv_pages[:10])))
                except Exception as exc:
                    errors.append(f"could not verify page audit: {exc}")
            if data_rows and any(str(r.get("source_pdf", "")).strip() != pdf.name for r in data_rows):
                errors.append("source_pdf provenance does not match the input PDF filename")
        else:
            for i, row in enumerate(data_rows, 2):
                for field in ("source_pdf", "page", "institution_code", "choice_code", "allocation_type", "category", "seats"):
                    if not str(row.get(field, "")).strip():
                        errors.append(f"row {i}: required field {field!r} is blank")
                        if len(errors) >= 50: break
                try:
                    if int(row.get("seats", "")) < 0: raise ValueError("seats must be non-negative")
                    if int(row.get("page", "")) < 1: raise ValueError("page must be >= 1")
                except (TypeError, ValueError) as exc:
                    errors.append(f"row {i}: invalid page/seats ({exc})")
                if len(errors) >= 50: break

        # Run the canonical project validator too, not just structural checks.
        # It checks category/lane/program vocabularies, duplicates, and seat
        # total reconciliation before any CSV can be labelled READY.
        if not errors:
            try:
                validation_code, validation_output = semantic_validate(target, kind, pdf)
                print(validation_output, flush=True)
                with log_path.open("a", encoding="utf-8") as log:
                    log.write("\n\n--- strict semantic validation ---\n")
                    log.write(validation_output + "\n")
                if validation_code != 0:
                    errors.append(
                        f"strict semantic validation failed (exit {validation_code}); "
                        "see the extraction log for category/program/seat-total details"
                    )
            except Exception as exc:
                errors.append(f"strict semantic validation could not run: {exc}")

        if errors:
            target.unlink(missing_ok=True)
            summary["files"].append({"pdf": pdf.name, "kind": kind, "status": "REVIEW_REQUIRED",
                                     "error_count": len(errors), "errors": errors[:50],
                                     "artifact": str(artifact), "log": str(log_path)})
            failures += 1
            continue
        summary["files"].append({"pdf": pdf.name, "kind": kind, "status": "READY",
                                 "csv": str(target), "bytes": target.stat().st_size, "log": str(log_path)})
        print(f"READY TO UPLOAD: {target}", flush=True)

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["status"] = "FAILED" if failures else "COMPLETED"
    report = REPORTS / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nRun report: {report}")
    print(f"Ready CSV folder: {READY}")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
