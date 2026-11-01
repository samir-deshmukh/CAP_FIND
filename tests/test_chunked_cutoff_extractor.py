import csv
import json
from pathlib import Path

import fitz

from scripts.chunked_cutoff_extractor import remap_chunk_artifacts, split_pdf


def test_split_pdf_preserves_requested_page_range(tmp_path: Path):
    source = fitz.open()
    for index in range(7):
        page = source.new_page()
        page.insert_text((72, 72), f"source-page-{index + 1}")
    part_path = tmp_path / "part.pdf"

    split_pdf(source, part_path, 2, 5)
    source.close()

    with fitz.open(part_path) as part:
        assert len(part) == 3
        text = [page.get_text() for page in part]
    assert ["source-page-3" in text[0], "source-page-4" in text[1],
            "source-page-5" in text[2]] == [True, True, True]


def test_remap_chunk_artifacts_restores_original_page_numbers(tmp_path: Path):
    stem = "part_0002"
    chunk_dir = tmp_path / stem
    chunk_dir.mkdir()
    csv_path = chunk_dir / f"{stem}_cutoffs.csv"
    json_path = chunk_dir / f"{stem}_cutoffs.json"
    audit_path = chunk_dir / f"{stem}_page_audit.json"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_pdf", "page", "rank"])
        writer.writeheader()
        writer.writerow({"source_pdf": f"{stem}.pdf", "page": 1, "rank": 123})
        writer.writerow({"source_pdf": f"{stem}.pdf", "page": 2, "rank": 456})
    json_path.write_text(json.dumps([
        {"source_pdf": f"{stem}.pdf", "page": 1, "rank": 123},
        {"source_pdf": f"{stem}.pdf", "page": 2, "rank": 456},
    ]), encoding="utf-8")
    audit_path.write_text(json.dumps([{"page": 1}, {"page": 2}]), encoding="utf-8")

    _, _, _, row_count = remap_chunk_artifacts(
        chunk_dir, stem, "original.pdf", page_offset=100
    )

    assert row_count == 2
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["page"] for row in rows] == ["101", "102"]
    assert all(row["source_pdf"] == "original.pdf" for row in rows)
    assert [row["page"] for row in json.loads(json_path.read_text())] == [101, 102]
    assert [row["page"] for row in json.loads(audit_path.read_text())] == [101, 102]


def test_backend_enforces_ten_page_cutoff_chunks():
    processing_source = (
        Path(__file__).resolve().parents[1] / "backend" / "admin" / "processing.py"
    ).read_text(encoding="utf-8")
    assert 'chunk_pages = "10"' in processing_source
