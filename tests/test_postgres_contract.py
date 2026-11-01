import os
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='TEST_DATABASE_URL is required')


def test_schema_and_unique_constraints():
    from scripts.db_bootstrap import bootstrap_schema, engine_for
    engine=engine_for(os.environ['TEST_DATABASE_URL']); bootstrap_schema(engine)
    with engine.begin() as c:
        tables={r[0] for r in c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))}
        required={'institutes','programs','base_categories','sections','stages','allocation_lanes','cutoffs','seats','staging_cutoffs','ingest_log','ingest_errors','staging_seats','seats_ingest_log','seats_ingest_errors'}
        assert required <= tables
        uniques=c.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN ('cutoffs','seats')")).scalars().all()
        assert any('UNIQUE' in x.upper() for x in uniques)


def test_upsert_is_idempotent():
    from scripts.db_bootstrap import bootstrap_schema, engine_for
    engine=engine_for(os.environ['TEST_DATABASE_URL']); bootstrap_schema(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO base_categories(base_code) VALUES('TEST_CONTRACT') ON CONFLICT(base_code) DO NOTHING"))
        c.execute(text("INSERT INTO base_categories(base_code) VALUES('TEST_CONTRACT') ON CONFLICT(base_code) DO NOTHING"))
        assert c.execute(text("SELECT count(*) FROM base_categories WHERE base_code='TEST_CONTRACT'")).scalar_one()==1
