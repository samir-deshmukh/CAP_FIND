from .db import connect

def ensure_part4_schema():
    # The PostgreSQL schema is created idempotently at startup. This function
    # remains as a compatibility hook for existing admin publish code.
    with connect() as c:
        # Program code is the authoritative join key between a cutoff branch
        # and the seat-matrix choice_code. Nullable for legacy rows; never infer
        # it from the branch display name.
        c.execute("ALTER TABLE cutoffs ADD COLUMN IF NOT EXISTS program_code TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cutoffs_inst_program_code ON cutoffs(institution_code, program_code)")
        # Local-worker upload tokens are stored separately from import_jobs so
        # SELECT j.* responses can never expose bearer-token hashes to browsers.
        c.execute("""CREATE TABLE IF NOT EXISTS local_worker_tokens (
            job_id INTEGER PRIMARY KEY REFERENCES import_jobs(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS local_worker_receipts (
            job_id INTEGER PRIMARY KEY REFERENCES import_jobs(id) ON DELETE CASCADE,
            artifact_sha256 TEXT NOT NULL,
            received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS worker_id TEXT")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS worker_lease_until TIMESTAMPTZ")
        c.execute("""CREATE TABLE IF NOT EXISTS import_worker_leases (
            job_id INTEGER PRIMARY KEY REFERENCES import_jobs(id) ON DELETE CASCADE,
            worker_id TEXT NOT NULL,
            lease_until TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_import_worker_leases_expiry ON import_worker_leases(lease_until)")
        c.execute("""CREATE TABLE IF NOT EXISTS remote_worker_heartbeats (
            worker_id TEXT PRIMARY KEY,
            last_seen TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            active_job_id INTEGER REFERENCES import_jobs(id) ON DELETE SET NULL
        )""")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS current_page INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS total_pages INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS current_chunk INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS total_chunks INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS source_deleted BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS source_deleted_at TIMESTAMPTZ")
        c.execute("CREATE INDEX IF NOT EXISTS idx_import_jobs_queue ON import_jobs(status,created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_import_events_job_type ON import_events(job_id,event_type)")
        # Indexes used by Review Center counts and latest-seat source coverage.
        c.execute("CREATE INDEX IF NOT EXISTS idx_import_staging_job_validation ON import_staging_records(job_id, validation_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_seats_coverage_latest ON seats(program_family, institution_code, capture_year, choice_code)")
        c.execute("ALTER TABLE data_releases ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
        c.execute("ALTER TABLE data_releases ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP")
        c.execute("ALTER TABLE data_releases ADD COLUMN IF NOT EXISTS manifest_json TEXT")
        c.execute("ALTER TABLE data_releases ADD COLUMN IF NOT EXISTS backup_path TEXT")
        c.execute("""CREATE TABLE IF NOT EXISTS cutoff_trend_points (program_family TEXT NOT NULL, institution_code TEXT NOT NULL, program_id INTEGER NOT NULL, base_category TEXT NOT NULL, is_ladies BOOLEAN NOT NULL DEFAULT FALSE, section_code TEXT NOT NULL, year INTEGER NOT NULL, round INTEGER NOT NULL, closing_percentile REAL NOT NULL, closing_rank INTEGER, PRIMARY KEY (program_family,institution_code,program_id,base_category,is_ladies,section_code,year,round))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cutoff_trend_lookup ON cutoff_trend_points(program_family,institution_code,base_category,is_ladies,section_code,year,round)")
        c.execute("""CREATE TABLE IF NOT EXISTS cutoff_college_year_summary (program_family TEXT NOT NULL, institution_code TEXT NOT NULL, year INTEGER NOT NULL, low_percentile REAL NOT NULL, high_percentile REAL NOT NULL, low_rank INTEGER, PRIMARY KEY (program_family,institution_code,year))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cutoff_summary_lookup ON cutoff_college_year_summary(program_family,institution_code,year)")
        c.execute("""CREATE TABLE IF NOT EXISTS cutoff_filter_options (program_family TEXT NOT NULL, institution_code TEXT NOT NULL, is_ladies BOOLEAN NOT NULL DEFAULT FALSE, year INTEGER NOT NULL, base_category TEXT NOT NULL, section_code TEXT NOT NULL, PRIMARY KEY (program_family,institution_code,is_ladies,year,base_category,section_code))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cutoff_options_lookup ON cutoff_filter_options(program_family,institution_code,is_ladies,year,base_category,section_code)")
        c.execute("""CREATE TABLE IF NOT EXISTS seat_matrix_runtime (program_family TEXT NOT NULL, institution_code TEXT NOT NULL, capture_year INTEGER NOT NULL, choice_code TEXT NOT NULL, allocation_lane TEXT NOT NULL, base_category TEXT NOT NULL, gender_g INTEGER, gender_l INTEGER, category_total INTEGER, is_total BOOLEAN NOT NULL DEFAULT FALSE, PRIMARY KEY (program_family,institution_code,capture_year,choice_code,allocation_lane,base_category,is_total))""")
        c.execute("ALTER TABLE seats ADD COLUMN IF NOT EXISTS source_row INTEGER")
        c.execute("CREATE INDEX IF NOT EXISTS idx_seat_runtime_lookup ON seat_matrix_runtime(program_family,institution_code,capture_year,choice_code,allocation_lane)")
        c.execute("""CREATE TABLE IF NOT EXISTS seat_matrix_courses (
            capture_year INTEGER NOT NULL,
            program_family TEXT NOT NULL,
            institution_code TEXT NOT NULL REFERENCES institutes(institution_code),
            choice_code TEXT NOT NULL,
            source_pdf TEXT NOT NULL,
            source_page INTEGER,
            source_job_id INTEGER,
            course_metadata JSONB NOT NULL,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (capture_year,program_family,institution_code,choice_code)
        )""")
        c.execute("ALTER TABLE seat_matrix_courses ADD COLUMN IF NOT EXISTS source_job_id INTEGER")
        c.execute("CREATE INDEX IF NOT EXISTS idx_seat_matrix_courses_lookup ON seat_matrix_courses(program_family,institution_code,capture_year,choice_code)")
        c.execute("CREATE TABLE IF NOT EXISTS derived_data_build_jobs (id SERIAL PRIMARY KEY, course_family TEXT, status TEXT NOT NULL DEFAULT 'QUEUED', progress INTEGER NOT NULL DEFAULT 0, message TEXT, started_at TIMESTAMP, finished_at TIMESTAMP, created_by INTEGER, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_derived_build_jobs_created ON derived_data_build_jobs(created_at DESC)")
