import hashlib

import pytest

from backend.admin.pipeline import MAX_PDF_BYTES, detect_course_family, detect_data_type, extract_pdf_metadata, identify, security_check
from backend.admin.processing import _resolve_cutoff_dimensions


def test_identify_cutoff_and_seat_filenames():
    assert identify("BCA_2026_C1.pdf") == ("CUTOFFS", "BCA", 2026, "C1", 1.0)
    assert identify("MCA_26_C2_SM.pdf") == ("SEATS", "MCA", 2026, "C2", 1.0)


def test_identifies_architecture_before_incidental_mba_reference(monkeypatch, tmp_path):
    pdf = tmp_path / "MBA_26_C1.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_text_probe",
        lambda path: "Bachelor of Architecture CAP Round 1 2026-27. Other admissions include MBA.",
    )
    assert identify(pdf.name) == ("CUTOFFS", "MBA", 2026, "C1", 1.0)
    assert extract_pdf_metadata(pdf, pdf.name) == ("BARCH", 2026, "C1")


def test_detects_common_course_families_without_substring_guessing():
    assert detect_course_family("BACHELOR OF ARCHITECTURE") == "BARCH"
    assert detect_course_family("First Year of Five Year Full Time Degree Course in Architecture") == "BARCH"
    assert detect_course_family("First Year of Five Year Full Time Degree Course in Architecture at College of Engineering and Technology") == "BARCH"
    assert detect_course_family("Two Years Full Time Post Graduate Degree Course in Engineering and Technology") == "ME"
    assert detect_course_family("Post Graduate Technical Courses in Engineering and Technology for working Professionals") == "ME"
    assert detect_course_family("Provisional Cutoff List for First Year of Full Time Master Program in M.PHARM & PHARM.D (Post Baccalaureate)") == "MPHARM"
    assert detect_course_family("Cut Off Merit for First Year Under Graduate Technical Course in B.Pharmacy & Post Graduate Pharm.D") == "BPHARM"
    assert detect_course_family("Admission to First Year of Post Graduate Technical Courses in Engineering/Technology (M.E./M.Tech.)") == "ME"
    assert detect_course_family("Cut Off List for Four Year Degree Courses in Engineering and Technology; M.E./M.Tech is mentioned elsewhere") == "BE"
    assert detect_course_family("Cut Off Merit for Post Graduate Technical Courses in Engineering/Technology (M.E./M.Tech.)") == "ME"
    assert detect_course_family("Cut Off List for CAP Round-IV Master of Computer Applications (MBA); 1005 College; M. B. A.") == "MBA"
    assert detect_course_family("Admission to First Year of Four Years Full Time Degree Course in Pharmacy (B.Pharm)") == "BPHARM"
    assert detect_course_family("B.Pharmacy CAP Seat Matrix") == "BPHARM"
    assert detect_course_family("MCA 2026 C1") == "MCA"
    assert detect_course_family("generic admission document") is None


def test_identify_partial_filename_has_partial_confidence():
    assert identify("BCA_results.pdf") == ("CUTOFFS", "BCA", None, None, 1 / 3)


def test_detect_data_type_uses_pdf_content(monkeypatch, tmp_path):
    pdf = tmp_path / "BCA 26 C1.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_text_probe",
        lambda path: "Provisional Seat Distribution Choice Code Course Name Category CAP Seats",
    )
    assert detect_data_type(pdf, pdf.name) == "SEATS"


def test_extract_pdf_metadata_recovers_seat_year(monkeypatch, tmp_path):
    pdf = tmp_path / "BBA.SM.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_text_probe",
        lambda path: "Provisional Seat Distribution for BBA / BMS Academic Year 2026-27",
    )
    assert extract_pdf_metadata(pdf, pdf.name) == ("BBA", 2026, None)


def test_extract_pdf_metadata_recovers_bare_session_year(monkeypatch, tmp_path):
    pdf = tmp_path / "MCA.SM.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_text_probe",
        lambda path: "Provisional Seat Distribution MCA 2026-27",
    )
    assert extract_pdf_metadata(pdf, pdf.name) == ("MCA", 2026, None)


def test_random_pdf_name_uses_course_heading_from_document(monkeypatch, tmp_path):
    pdf = tmp_path / "scan_8f3a19.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_text_probe",
        lambda path: "CAP Round II. Bachelor of Computer Applications. Academic Year 2025-26.",
    )

    assert extract_pdf_metadata(pdf, pdf.name) == ("BCA", 2025, "C2")


def test_local_metadata_uses_ocr_when_scanned_pdf_has_no_native_text(monkeypatch, tmp_path):
    pdf = tmp_path / "scan_8f3a19.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr("backend.admin.pipeline._pdf_text_probe", lambda path: "")
    monkeypatch.setattr(
        "backend.admin.pipeline._pdf_ocr_probe",
        lambda path: "Bachelor of Computer Applications CAP Round 2 2025-26",
    )

    assert extract_pdf_metadata(pdf, pdf.name, use_ocr=True) == ("BCA", 2025, "C2")


def test_scanned_pdf_reports_missing_tesseract(monkeypatch, tmp_path):
    from backend.admin.pipeline import _pdf_ocr_probe

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setattr("backend.admin.pipeline.shutil.which", lambda command: None)

    with pytest.raises(RuntimeError, match="Tesseract OCR program is missing"):
        _pdf_ocr_probe(pdf)


def test_security_check_accepts_pdf_and_returns_sha256(tmp_path):
    pdf = tmp_path / "sample.pdf"
    payload = b"%PDF-1.7\nminimal test content"
    pdf.write_bytes(payload)

    size, digest = security_check(pdf)

    assert size == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("sample.txt", b"%PDF-1.7", "extension"),
        ("sample.pdf", b"not a pdf", "valid PDF"),
    ],
)
def test_security_check_rejects_invalid_upload(tmp_path, filename, payload, message):
    path = tmp_path / filename
    path.write_bytes(payload)

    with pytest.raises(ValueError, match=message):
        security_check(path)


def test_security_check_rejects_oversized_pdf(tmp_path, monkeypatch):
    path = tmp_path / "large.pdf"
    path.write_bytes(b"%PDF-" + b"x" * 10)
    monkeypatch.setattr("backend.admin.pipeline.MAX_PDF_BYTES", 5)

    with pytest.raises(ValueError, match="PDF exceeds"):
        security_check(path)


def test_cutoff_dimension_fallbacks_match_validator_semantics():
    # These are real states present in the trusted BCA_26_C3 artifact:
    # section can be blank because the category suffix determines H/O/S,
    # and stage can be blank and is canonically represented as Unknown.
    assert _resolve_cutoff_dimensions({
        "category": "MI",
        "section": "",
        "stage": "",
    }) == ("MI", False, "SL", "Unknown")

    assert _resolve_cutoff_dimensions({
        "category": "GOPENH",
        "section": "",
        "stage": "Stage-I",
    }) == ("OPEN", False, "HU", "Stage-I")

    with pytest.raises(ValueError, match="Unknown section"):
        _resolve_cutoff_dimensions({
            "category": "GOPENH",
            "section": "Not A Section",
            "stage": "Stage-I",
        })

    with pytest.raises(ValueError, match="Unknown stage"):
        _resolve_cutoff_dimensions({
            "category": "GOPENH",
            "section": "Home University Seats Allotted to Home University Candidates",
            "stage": "Stage-XX",
        })
