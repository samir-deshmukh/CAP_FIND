from scripts.refresh_derived_data import _engineering_cutoff_seat_coverage


class FakeResult:
    def mappings(self):
        return self

    def one(self):
        return {"unmatched_same_year": 27, "no_same_year_matrix": 45}


class FakeConnection:
    def __init__(self):
        self.sql = ""

    def execute(self, statement):
        self.sql = " ".join(str(statement).split())
        return FakeResult()


def test_engineering_coverage_compares_only_matching_institution_and_year():
    connection = FakeConnection()

    coverage = _engineering_cutoff_seat_coverage(connection)

    assert coverage == {"unmatched_same_year": 27, "no_same_year_matrix": 45}
    assert "sy.capture_year = cp.year" in connection.sql
    assert "sc.capture_year = cp.year" in connection.sql
    assert "sy.institution_code = cp.institution_code" in connection.sql
    assert "sc.choice_code = cp.program_code" in connection.sql
    assert "MAX(s2.capture_year)" not in connection.sql


def test_engineering_coverage_handles_zero_counts():
    class EmptyResult:
        def mappings(self):
            return self

        def one(self):
            return {"unmatched_same_year": None, "no_same_year_matrix": 0}

    class EmptyConnection:
        def execute(self, statement):
            return EmptyResult()

    assert _engineering_cutoff_seat_coverage(EmptyConnection()) == {
        "unmatched_same_year": 0,
        "no_same_year_matrix": 0,
    }
