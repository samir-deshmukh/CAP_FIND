"""Database test policy: production code is PostgreSQL-only."""
import os
import pytest

def pytest_collection_modifyitems(config, items):
    if os.getenv('TEST_DATABASE_URL'):
        return
    marker=pytest.mark.skip(reason='PostgreSQL integration test requires TEST_DATABASE_URL')
    for item in items:
        if 'integration' in item.nodeid or item.module.__name__.endswith('test_postgres_contract'):
            item.add_marker(marker)
