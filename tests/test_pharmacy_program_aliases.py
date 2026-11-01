import csv
from pathlib import Path


def test_2023_pharmacy_cutoff_program_names_are_recognized():
    path = Path(__file__).resolve().parents[1] / "data" / "reference" / "program_aliases.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        aliases = {row["raw_name"]: row for row in csv.DictReader(handle)}

    assert aliases["Pharmacy"]["program_family"] == "BPHARM"
    assert aliases["Pharmacy"]["program_full"] == "Bachelor of Pharmacy"
    assert aliases["Pharm D ( Doctor of Pharmacy)"]["program_family"] == "PHARMD"
    assert aliases["Pharm D ( Doctor of Pharmacy)"]["program_full"] == "Doctor of Pharmacy"
