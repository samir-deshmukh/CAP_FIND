from scripts.seat_matrix_extractor import parse_course_block


def test_seat_matrix_parser_preserves_original_summary_labels_and_values():
    table = [
        ["Choice Code", "Course Name", "SI", "MS Seats", "Minority Seats", "All India"],
        ["0100219110", "Civil Engineering", "60", "60", "0", "0"],
        ["Category", "OPEN", "SC", "Total"],
        ["General / Ladies"],
        ["State Level", "16", "6", "6", "2", "22"],
        ["PWD", "1", "0", "1"],
        ["PWD Common Reserved Seats: 1"],
        ["DEF", "0", "0", "0"],
        ["DEF Common Reserved Seats: 1"],
        ["Economically Weaker Section (EWS) Seats: 6"],
    ]
    course, rows, _ = parse_course_block(
        1, table, 0, "01002", "Government College of Engineering, Amravati",
        "Autonomous Institute", "Government Autonomous", 60,
    )
    assert course["choice_code"] == "0100219110"
    assert course["course_name"] == "Civil Engineering"
    assert course["summary_fields"] == {
        "SI": 60,
        "MS Seats": 60,
        "Minority Seats": 0,
        "All India": 0,
    }
    assert course["cap_seats"] == 60
    assert course["pwd_common_reserved"] == 1
    assert course["def_common_reserved"] == 1
    assert course["ews_seats"] == 6
    assert rows


def test_seat_matrix_metadata_is_not_reconstructed_from_slugged_columns():
    table = [
        ["Choice Code", "Course Name", "SI", "MS Seats", "OrphanI", "OrphanN"],
        ["0301224510", "Computer Engineering", "60", "60", "1", "0"],
        ["Category", "OPEN", "Total"],
        ["General / Ladies"],
        ["State Level", "20", "5", "25"],
        ["PWD", "1", "1"],
        ["DEF", "1", "1"],
        ["Economically Weaker Section (EWS) Seats: 6"],
    ]
    course, _, _ = parse_course_block(
        7, table, 0, "03012", "Veermata Jijabai Technological Institute",
        "Autonomous Institute", "Government-Aided Autonomous", 60,
    )
    assert course["summary_fields"] == {
        "SI": 60, "MS Seats": 60, "OrphanI": 1, "OrphanN": 0,
    }
    assert course["orphani"] == 1
    assert course["orphann"] == 0


def test_admin_import_stores_compact_metadata_once_with_source_job(monkeypatch):
    import json
    from backend.admin.processing import _insert_seat_course_metadata

    class FakeConnection:
        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params):
            self.sql = sql
            self.params = params
            return None

    connection = FakeConnection()
    raw = {
        "source_pdf": "2026_fe_seatmatrix_V1.pdf",
        "page": "1",
        "institution_code": "01002",
        "choice_code": "0100219110",
        "course_metadata": json.dumps({
            "course_name": "Civil Engineering",
            "summary_fields": {"SI": 60, "MS Seats": 60},
            "cap_seats": 60,
        }),
    }
    job = {"id": 91, "year": 2026, "course_family": "BE"}
    assert _insert_seat_course_metadata(connection, raw, job, "uploaded.csv") is True
    assert "seat_matrix_courses" in connection.sql
    assert "ON CONFLICT(capture_year,program_family,institution_code,choice_code) DO NOTHING" in connection.sql
    assert connection.params[:7] == (
        2026, "BE", "01002", "0100219110", "2026_fe_seatmatrix_V1.pdf", 1, 91
    )
    stored = json.loads(connection.params[7])
    assert stored["course_name"] == "Civil Engineering"
    assert stored["summary_fields"] == {"SI": 60, "MS Seats": 60}
