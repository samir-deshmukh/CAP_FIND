"""Source-file provenance tests for staged CSV imports."""

from backend.admin.processing import _source_pdf_for_record


def test_csv_row_source_pdf_takes_precedence_over_uploaded_csv_name():
    assert _source_pdf_for_record(
        {"source_pdf": "BCA 2026 CAP Round 1.pdf"},
        "BCA 2026 CAP Round 1 cutoffs.csv",
    ) == "BCA 2026 CAP Round 1.pdf"


def test_missing_or_blank_row_source_pdf_falls_back_to_uploaded_filename():
    fallback = "BCA 2026 CAP Round 1 cutoffs.csv"

    assert _source_pdf_for_record({}, fallback) == fallback
    assert _source_pdf_for_record({"source_pdf": "   "}, fallback) == fallback
