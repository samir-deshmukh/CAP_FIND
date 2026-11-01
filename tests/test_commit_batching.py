from backend.admin.processing import _iter_staged_rows, _iter_release_items


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _PagedConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        job_id, result_type, last_id, batch_size = params
        assert job_id == 91
        assert result_type == "SEATS"
        return _Result([
            row for row in self.rows
            if row["id"] > last_id and row["job_id"] == job_id and row["result_type"] == result_type
        ][:batch_size])


def test_iter_staged_rows_uses_bounded_keyset_pages():
    rows = [
        {"id": index, "job_id": 91, "result_type": "SEATS", "normalized_json": str(index)}
        for index in range(1, 8)
    ]
    connection = _PagedConnection(rows)

    result = list(_iter_staged_rows(connection, 91, "SEATS", batch_size=3))

    assert [row["id"] for row in result] == list(range(1, 8))
    assert [call[1][2:] for call in connection.calls] == [(0, 3), (3, 3), (6, 3), (7, 3)]
    assert all("id>?" in query and "LIMIT ?" in query for query, _ in connection.calls)


class _ReleaseConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        release_id, cursor, batch_size = params
        if "id<?" in query:
            candidates = [row for row in self.rows if row["release_id"] == release_id and row["id"] < cursor]
            return _Result(sorted(candidates, key=lambda row: row["id"], reverse=True)[:batch_size])
        candidates = [row for row in self.rows if row["release_id"] == release_id and row["id"] > cursor]
        return _Result(sorted(candidates, key=lambda row: row["id"])[:batch_size])


def test_release_ledger_iteration_is_bounded_in_both_directions():
    rows = [{"id": index, "release_id": 6} for index in range(1, 8)]
    ascending_conn = _ReleaseConnection(rows)
    descending_conn = _ReleaseConnection(rows)

    ascending = list(_iter_release_items(ascending_conn, 6, batch_size=3))
    descending = list(_iter_release_items(descending_conn, 6, newest_first=True, batch_size=3))

    assert [row["id"] for row in ascending] == list(range(1, 8))
    assert [row["id"] for row in descending] == list(range(7, 0, -1))
    assert all("LIMIT ?" in query for query, _ in ascending_conn.calls + descending_conn.calls)
