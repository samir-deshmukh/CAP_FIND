from pathlib import Path

import pandas as pd
import pytest

from scripts.cutoff_extractor import (
    clean_text,
    detect_section,
    extract_category_tokens,
    get_priority,
    is_category_token,
    split_by_stage,
    parse_structured_page,
    deduplicate_and_merge,
)
from scripts.validate_data import (
    forward_fill_block_columns,
    is_extraction_anomaly,
    parse_category,
    parse_filename as parse_cutoff_filename,
)
from scripts.validate_seats import parse_filename as parse_seat_filename


def test_cutoff_token_helpers():
    assert is_category_token("GOPENH")
    assert not is_category_token("STAGE")
    assert not is_category_token("12")
    assert extract_category_tokens("GOPENH LOPENH") == ["GOPENH", "LOPENH"]
    assert extract_category_tokens("GOPENH 12") == []


def test_cutoff_text_and_section_helpers():
    assert clean_text(" A\r\n\r\n\r\nB ") == "A\n\nB"
    assert detect_section("Home University Seats Allotted to Home University Candidates")
    assert detect_section("not a section") is None


def test_cutoff_stage_split_and_priority():
    assert split_by_stage("Stage-I 88.5 Stage-II 90.0") == [
        ("Stage-I", "88.5"),
        ("Stage-II", "90.0"),
    ]
    assert get_priority("native") > get_priority("ocr")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GOPENH", ("OPEN", False, "HU")),
        ("LSCS", ("SC", True, "SL")),
        ("PWDROBCH", ("PWDROBC", False, "HU")),
        ("MI", ("MI", False, "SL")),
        ("MI-MH", ("MI", False, "SL")),
        ("MH", ("MI", False, "SL")),
        ("DEFRNT1S", ("DEFRNT1", False, "SL")),
        ("DEFRNT2S", ("DEFRNT2", False, "SL")),
        ("DEFRNT3S", ("DEFRNT3", False, "SL")),
        ("DEFRSTS", ("DEFRST", False, "SL")),
        ("DEFRVJS", ("DEFRVJ", False, "SL")),
        ("PWDRNT1S", ("PWDRNT1", False, "SL")),
        ("PWDRNT2S", ("PWDRNT2", False, "SL")),
        ("PWDRNT3S", ("PWDRNT3", False, "SL")),
        ("PWDRSTS", ("PWDRST", False, "SL")),
        ("PWDRSTH", ("PWDRST", False, "HU")),
        ("PWDRVJS", ("PWDRVJ", False, "SL")),
        ("", (None, None, None)),
    ],
)
def test_parse_category_rules(raw, expected):
    assert parse_category(raw) == expected


def test_parser_tracks_multiple_program_blocks_on_one_page_and_continuation():
    context = {
        "institution_code": "", "institution_name": "", "program_code": "",
        "program_name": "", "status": "", "home_university": "",
    }
    lines = [
        "01002 - College A",
        "0100219110 - Civil Engineering",
        "Status: Government Autonomous Home University : Autonomous Institute",
        "State Level", "I", "GOPENS GSCS", "100 (90.0) 200 (80.0)",
        "0100219120 - Computer Engineering",
        "Status: Government Autonomous Home University : Autonomous Institute",
        "State Level", "I", "GOPENS GSCS", "100 (90.0) 200 (80.0)",
    ]
    records = parse_structured_page(1, lines, "native_text", context)
    assert [(r["program_code"], r["program_name"], r["category"], r["rank"])
            for r in records] == [
        ("0100219110", "Civil Engineering", "GOPENS", "100"),
        ("0100219110", "Civil Engineering", "GSCS", "200"),
        ("0100219120", "Computer Engineering", "GOPENS", "100"),
        ("0100219120", "Computer Engineering", "GSCS", "200"),
    ]
    continuation = parse_structured_page(
        2, ["State Level", "I", "PWDRNT1S", "300 (70.0)"],
        "native_text", dict(context),
    )
    assert len(continuation) == 1
    assert continuation[0]["program_name"] == "Computer Engineering"
    assert continuation[0]["program_code"] == "0100219120"


def test_parser_joins_wrapped_program_title_before_status_metadata():
    context = {
        "institution_code": "", "institution_name": "", "program_code": "",
        "program_name": "", "status": "", "home_university": "",
    }
    parser_state = {"section": None, "stage": ""}
    lines = [
        "03146 - Example College",
        "0314692010 - Computer Science and Engineering (Internet of Things and Cyber Security Including Block Chain",
        "Technology)",
        "Status:",
        "Un-Aided Home University : Mumbai University",
        "State Level", "I", "GOPENH", "60838 (85.3954204)",
    ]
    records = parse_structured_page(1, lines, "native_text", context, parser_state)
    assert len(records) == 1
    assert records[0]["program_code"] == "0314692010"
    assert records[0]["program_name"] == (
        "Computer Science and Engineering (Internet of Things and Cyber Security Including Block Chain Technology)"
    )


def test_deduplication_does_not_merge_same_rank_from_different_programs():
    common = {"source_pdf": "sample.pdf", "page": 1, "institution_code": "01002",
              "section": "State Level", "category": "GOPENS", "rank": "100"}
    rows = [
        {**common, "program_code": "0100219110", "program_name": "Civil Engineering"},
        {**common, "program_code": "0100219120", "program_name": "Computer Engineering"},
    ]
    assert len(deduplicate_and_merge(rows)) == 2


def test_forward_fill_only_uses_prior_nonblank_values():
    df = pd.DataFrame(
        {
            "institution_code": ["01102", "", "01103"],
            "institution_name": ["College A", "", "College B"],
            "program_code": ["101", "", "202"],
            "program_name": ["BCA", "", "MBA"],
            "status": ["Status A", "", "Status B"],
            "section": ["HU", "", "SL"],
            "home_university": ["University A", "", "University B"],
        }
    )

    count, first_blank = forward_fill_block_columns(df)

    assert count == 6
    assert first_blank == []
    assert df.loc[1, "institution_code"] == "01102"
    assert df.loc[1, "program_name"] == "BCA"


def test_extraction_anomaly_detection():
    assert is_extraction_anomaly(
        {"institution_code": "", "institution_name": "", "category": "OPEN"}
    )
    assert is_extraction_anomaly(
        {"institution_code": "01102", "institution_name": "College", "category": "GOVERNMENT"}
    )
    assert not is_extraction_anomaly(
        {"institution_code": "01102", "institution_name": "College", "category": "OPEN"}
    )


def test_validation_filename_parsers():
    assert parse_cutoff_filename(Path("BCA_26_C1.csv")) == {
        "family": "BCA",
        "year": 2026,
        "round": 1,
    }
    assert parse_cutoff_filename(Path("unknown.csv")) is None
    assert parse_seat_filename(Path("BCA_SM.csv")) == {"family": "BCA"}
    assert parse_seat_filename(Path("random.csv")) is None
