# Local folder-based PDF extraction

This workflow runs CAPFind's existing extraction scripts on the PC. The original PDFs remain local; the generated canonical CSV is uploaded to the Admin Panel for the existing server-side validation, staging, review, and commit workflow.

## Run in VS Code

1. Open the `cet` directory in VS Code.
2. Copy PDFs into `cet/local_extraction/input/`.
3. Ensure each filename indicates its type:
   - Cutoff PDFs: include `cutoff`, `cut_off`, `CAP1`, `CAP2`, `CAP3`, or `CAP4`.
   - Seat matrix PDFs: include `seatmatrix`, `seat_matrix`, or `SM`.
4. Open the VS Code terminal in `cet` and run `./run_local_extraction.sh`.
5. Upload only final CSV files from `cet/local_extraction/ready_to_upload/`. Do not upload intermediate chunk files.
6. Review `cet/local_extraction/reports/` if any file fails.

## Output folders

- `local_extraction/input/`: source PDFs.
- `local_extraction/output/<PDF stem>/`: per-PDF extraction artifacts and resumable chunk manifest.
- `local_extraction/ready_to_upload/`: final CSV files only.
- `local_extraction/reports/`: per-PDF logs and run summaries.

## Options

- Use smaller cutoff chunks on a low-memory PC: `./run_local_extraction.sh --chunk-pages 5`.
- Enable OCR fallback for cutoff PDFs: `./run_local_extraction.sh --hybrid`. OCR requires Tesseract and the configured Python dependencies.

The default cutoff chunk size is 10 pages. The extractor preserves page references and retries individual failed cutoff chunks up to three times. Keep the same PDF and output directory when resuming a failed cutoff extraction.

The runner expects the existing environment at `~/.venvs/capfind-local-worker`. If it is missing, recreate it using `cet/requirements-dev.txt` and the setup instructions in `LOCAL_EXTRACTION_WORKER.md`.

## CSV upload metadata

The Import Center detects cutoff versus seat-matrix data from canonical CSV columns, and detects course/year/CAP round from the `source_pdf` value. Use informative source filenames such as `2026ENGG_CAP1_MH_CutOff_V1.pdf` and `2026_fe_seatmatrix_V1.pdf`. Cutoff filenames must identify CAP1, CAP2, CAP3, or CAP4. The server still validates the uploaded CSV; inference is not a validation bypass.
