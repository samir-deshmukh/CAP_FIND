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
