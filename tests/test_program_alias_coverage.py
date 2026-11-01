import csv
from pathlib import Path
from scripts.validate_data import is_valid_program_identity

def test_2024_engineering_cutoff_program_names_are_recognized():
    path = Path(__file__).resolve().parents[1] / "data" / "reference" / "program_aliases.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        aliases = {row["raw_name"]: row for row in csv.DictReader(handle)}

    expected = {
        "Electrical Engg[Electronics and Power]",
        "Mechanical & Automation Engineering",
        "Printing and Packing Technology",
        "5G",
        "VLSI",
        "Architectural Assistantship",
        "Data Engineering",
        "Fire Engineering",
        "Electronics and Telecommunication",
    }
    assert expected <= aliases.keys()
    assert aliases["Electrical Engg[Electronics and Power]"]["program_full"] == "Electrical Engineering (Electronics and Power)"
    assert aliases["Mechanical & Automation Engineering"]["program_full"] == "Mechanical and Automation Engineering"
    assert aliases["Printing and Packing Technology"]["program_full"] == "Printing and Packaging Technology"
    assert all(aliases[name]["program_family"] == "BE" for name in expected)


def test_new_course_branch_with_official_program_code_is_validated_as_source_data():
    row = {
        "program_name": "Electronics and Telecommunication",
        "program_code": "0568837310",
        "source_pdf": "randomized_upload_name.pdf",
    }
    assert is_valid_program_identity(row, set())


def test_unlisted_program_without_clean_source_identity_stays_invalid():
    assert not is_valid_program_identity(
        {"program_name": "New branch", "program_code": "", "source_pdf": "input.pdf"},
        set(),
    )
    assert not is_valid_program_identity(
        {
            "program_name": "New branch Status: Un-Aided",
            "program_code": "0568837310",
            "source_pdf": "input.pdf",
        },
        set(),
    )
