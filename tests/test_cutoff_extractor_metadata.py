"""Tests for cutoff PDF metadata recovery, wrapped program headings and stage interpretation."""

from scripts.cutoff_extractor import (
    extract_metadata,
    merge_split_rank_lines,
    update_metadata_from_line,
)


def test_split_status_and_home_university_metadata_are_recovered():
    lines = merge_split_rank_lines([
        '01102 - Example College, Amravati',
        '0110210110 - BCA',
        'Status:',
        'Un-Aided Linguistic Minority - Hindi Home University : Sant Gadge Baba Amravati University',
        'Home University Seats Allotted to Home University Candidates',
    ])
    meta = extract_metadata(lines)
    assert meta['institution_code'] == '01102'
    assert meta['status'] == 'Un-Aided Linguistic Minority - Hindi'
    assert meta['home_university'] == 'Sant Gadge Baba Amravati University'


def test_inline_status_and_home_university_are_split():
    lines = [
        '01102 - Example College, Amravati',
        '0110210110 - BCA',
        'Status: Un-Aided Linguistic Minority - Hindi Home University : Sant Gadge Baba Amravati University',
    ]
    meta = extract_metadata(lines)
    assert meta['institution_code'] == '01102'
    assert meta['status'] == 'Un-Aided Linguistic Minority - Hindi'
    assert meta['home_university'] == 'Sant Gadge Baba Amravati University'


def test_extractor_loads_hybrid_pdf_backend_on_demand():
    from scripts import cutoff_extractor

    assert cutoff_extractor.fitz.__name__ == "fitz"
    assert cutoff_extractor.fitz_pdfium is None
    cutoff_extractor._ensure_pdfium_loaded()
    assert cutoff_extractor.fitz_pdfium.__name__.endswith("fitz_pdfium")


def test_program_code_with_letter_suffix_is_parsed():
    lines = merge_split_rank_lines([
        '01313 - Example College',
        '0131310170U - BCA',
    ])
    meta = extract_metadata(lines)
    assert meta['program_code'] == '0131310170U'
    assert meta['program_name'] == 'BCA'


def test_inline_program_status_and_university_do_not_contaminate_program_name():
    line = (
        '0314692010 - Computer Science and Engineering '
        '(Internet of Things and Cyber Security Including Block Chain Technology) '
        'Status: Un-Aided Home University : Mumbai University'
    )
    meta = {
        'institution_code': '03146', 'institution_name': 'Example College',
        'program_code': '', 'program_name': '', 'status': '', 'home_university': '',
    }

    assert update_metadata_from_line(line, meta) == 'program'
    assert meta['program_name'] == (
        'Computer Science and Engineering '
        '(Internet of Things and Cyber Security Including Block Chain Technology)'
    )
    assert meta['status'] == 'Un-Aided'
    assert meta['home_university'] == 'Mumbai University'


def test_wrapped_program_name_and_inline_metadata_are_separated():
    meta = {
        'institution_code': '03146', 'institution_name': 'Example College',
        'program_code': '', 'program_name': '', 'status': '', 'home_university': '',
    }
    state = {}
    assert update_metadata_from_line(
        '0314692010 - Computer Science and Engineering '
        '(Internet of Things and Cyber Security Including Block Chain', meta, state
    ) == 'program'
    assert update_metadata_from_line(
        'Technology) Status: Un-Aided Home University : Mumbai University', meta, state
    ) == 'program_continuation'

    assert meta['program_name'] == (
        'Computer Science and Engineering '
        '(Internet of Things and Cyber Security Including Block Chain Technology)'
    )
    assert meta['status'] == 'Un-Aided'
    assert meta['home_university'] == 'Mumbai University'


def test_extract_metadata_splits_program_header_metadata():
    lines = [
        '03146 - Example College',
        '0314692010 - Computer Science and Engineering (Internet of Things and Cyber Security Including Block Chain Technology) Status: Un-Aided Home University : Mumbai University',
    ]

    meta = extract_metadata(lines)

    assert meta['program_name'] == (
        'Computer Science and Engineering '
        '(Internet of Things and Cyber Security Including Block Chain Technology)'
    )
    assert meta['status'] == 'Un-Aided'
    assert meta['home_university'] == 'Mumbai University'


def test_bare_roman_rank_layout_is_not_promoted_to_stage():
    lines = merge_split_rank_lines([
        'GOPENH LOPENH',
        'I 2414',
        '(55.0372530)',
        '1047',
        '(75.3093618)',
    ])
    assert lines[0] == 'GOPENH LOPENH'
    assert lines[1] == 'I 2414 (55.0372530)'
    assert lines[2] == '1047 (75.3093618)'


def test_sparse_cutoff_header_mismatch_quarantines_category_labels():
    from scripts.cutoff_extractor import parse_structured_page

    metadata = {
        "institution_code": "01001", "institution_name": "Example",
        "program_code": "0100101010", "program_name": "BCA",
        "status": "", "home_university": "",
    }
    records = parse_structured_page(
        28,
        ["GOBCS TFWS DEFOPENS PWDOPENS", "4054 (99.1) 1955 (98.2) 4760 (97.3)"],
        "fixture.pdf", metadata,
    )
    # Three cutoff values against four category labels cannot be paired safely.
    # The parser must preserve the values but leave category labels blank for review.
    assert len(records) == 3
    assert all(row["category"] == "" for row in records)
    assert all(row["category_mapping_status"] == "ambiguous_count_mismatch" for row in records)


def test_merit_metric_flags_postgraduate_score_sources():
    from scripts.cutoff_extractor import classify_merit_metric

    assert classify_merit_metric("BCA") == "percentile"
    assert classify_merit_metric("M.E. Computer Engineering") == "score_or_marks_source_label_required"
    assert classify_merit_metric("M.Tech Working Professional") == "score_or_marks_source_label_required"


def test_maharashtra_state_candidature_minority_section_is_recognized():
    from scripts.cutoff_extractor import detect_section

    section = detect_section(
        "Minority Seats Allotted to Maharashtra State Candidature Candidates"
    )
    assert section == "Minority Seats Allotted to Maharashtra State Candidature Candidates"
