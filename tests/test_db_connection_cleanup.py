import pytest

from backend.admin.db import Connection


class FakeSQLAlchemyConnection:
    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.closed = False

    def commit(self):
        if self.fail_on == "commit":
            raise RuntimeError("commit failed")

    def rollback(self):
        if self.fail_on == "rollback":
            raise RuntimeError("rollback failed")

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("fail_on", "exc_type"),
    [("commit", None), ("rollback", RuntimeError)],
)
def test_connection_always_closes_if_transaction_finalization_fails(fail_on, exc_type):
    connection = Connection.__new__(Connection)
    connection._conn = FakeSQLAlchemyConnection(fail_on)

    if exc_type is None:
        with pytest.raises(RuntimeError, match="commit failed"):
            connection.__exit__(None, None, None)
    else:
        error = RuntimeError("body failed")
        with pytest.raises(RuntimeError, match="rollback failed"):
            connection.__exit__(RuntimeError, error, None)

    assert connection._conn.closed
