-- CET CAP Decision Support — PostgreSQL Schema
-- Compatible with PostgreSQL 13+ (Local PostgreSQL, Neon, Supabase, RDS)

-- ============================================================
-- REFERENCE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS institutes (
    institution_code   TEXT PRIMARY KEY,
    institution_name   TEXT NOT NULL,
    home_university    TEXT,
    institute_type     TEXT,
    affiliation_status TEXT,
    city               TEXT,
    district           TEXT,
    address            TEXT,
    website            TEXT,
    city_source        TEXT,
    website_source     TEXT,
    address_source     TEXT,
    verified_at        TIMESTAMP,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS programs (
    program_id         SERIAL PRIMARY KEY,
    program_family     TEXT NOT NULL,
    program_name_raw   TEXT NOT NULL,
    level              TEXT,
    UNIQUE(program_family, program_name_raw)
);

CREATE TABLE IF NOT EXISTS base_categories (
    base_code      TEXT PRIMARY KEY,
    category_full  TEXT,
    category_group TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    section_code TEXT PRIMARY KEY,
    section_full TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stages (
    stage_code TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS allocation_lanes (
    lane_code TEXT PRIMARY KEY,
    lane_full TEXT NOT NULL
);

-- ============================================================
-- FACT TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS cutoffs (
    id               SERIAL PRIMARY KEY,
    year             INTEGER NOT NULL,
    round            INTEGER NOT NULL,
    institution_code TEXT NOT NULL REFERENCES institutes(institution_code),
    program_id       INTEGER NOT NULL REFERENCES programs(program_id),
    program_code     TEXT,
    base_category    TEXT NOT NULL REFERENCES base_categories(base_code),
    is_ladies        BOOLEAN NOT NULL DEFAULT FALSE,
    section_code     TEXT NOT NULL REFERENCES sections(section_code),
    stage_code       TEXT NOT NULL REFERENCES stages(stage_code),
    home_university  TEXT,
    rank_number      INTEGER,
    rank_suffix      TEXT,
    percentile       REAL NOT NULL,
    raw_category     TEXT NOT NULL,
    raw_program_name TEXT NOT NULL,
    source_pdf       TEXT NOT NULL,
    source_page      INTEGER,
    ingested_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, round, institution_code, program_id,
           base_category, is_ladies, section_code, stage_code,
           rank_number, percentile)
);

CREATE INDEX IF NOT EXISTS idx_cutoffs_filter
    ON cutoffs(year, round, program_id, base_category,
               is_ladies, section_code);

CREATE INDEX IF NOT EXISTS idx_cutoffs_inst_prog
    ON cutoffs(institution_code, program_id);
CREATE INDEX IF NOT EXISTS idx_cutoffs_inst_program_code
    ON cutoffs(institution_code, program_code);

CREATE INDEX IF NOT EXISTS idx_cutoffs_percentile
    ON cutoffs(percentile DESC);

CREATE INDEX IF NOT EXISTS idx_cutoffs_program_percentile_inst
    ON cutoffs(program_id, percentile, institution_code);

CREATE TABLE IF NOT EXISTS seats (
    id                  SERIAL PRIMARY KEY,
    capture_year        INTEGER NOT NULL,
    program_family      TEXT NOT NULL,
    institution_code    TEXT NOT NULL REFERENCES institutes(institution_code),
    choice_code         TEXT NOT NULL,
    allocation_lane     TEXT NOT NULL REFERENCES allocation_lanes(lane_code),
    base_category       TEXT REFERENCES base_categories(base_code),
    is_total            BOOLEAN NOT NULL DEFAULT FALSE,
    is_ladies           BOOLEAN,
    seats               INTEGER NOT NULL,
    raw_category        TEXT NOT NULL,
    raw_allocation_type TEXT NOT NULL,
    raw_gender          TEXT NOT NULL DEFAULT '',
    source_pdf          TEXT NOT NULL,
    source_page         INTEGER,
    source_row          INTEGER,
    ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(capture_year, program_family, institution_code, choice_code,
           allocation_lane, raw_category, raw_gender)
);

CREATE INDEX IF NOT EXISTS idx_seats_lookup
    ON seats(institution_code, choice_code, capture_year);

CREATE INDEX IF NOT EXISTS idx_seats_category
    ON seats(base_category, allocation_lane, is_total);

-- Full per-choice-code metadata copied from the official seat-matrix PDF.
-- Long allocation rows alone are insufficient to reproduce the source table:
-- this JSONB record retains the original summary columns and reservation notes.
CREATE TABLE IF NOT EXISTS seat_matrix_courses (
    capture_year INTEGER NOT NULL,
    program_family TEXT NOT NULL,
    institution_code TEXT NOT NULL REFERENCES institutes(institution_code),
    choice_code TEXT NOT NULL,
    source_pdf TEXT NOT NULL,
    source_page INTEGER,
    source_job_id INTEGER,
    course_metadata JSONB NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (capture_year, program_family, institution_code, choice_code)
);
CREATE INDEX IF NOT EXISTS idx_seat_matrix_courses_lookup
    ON seat_matrix_courses(program_family, institution_code, capture_year, choice_code);

-- ============================================================
-- STAGING & AUDIT TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS staging_cutoffs (
    id          SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    raw_row     TEXT NOT NULL,
    loaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed   BOOLEAN DEFAULT FALSE,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id             SERIAL PRIMARY KEY,
    source_file    TEXT NOT NULL,
    rows_read      INTEGER,
    rows_inserted  INTEGER,
    rows_skipped   INTEGER,
    rows_duplicate INTEGER DEFAULT 0,
    rows_failed    INTEGER,
    ingested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingest_errors (
    id           SERIAL PRIMARY KEY,
    source_file  TEXT NOT NULL,
    source_page  INTEGER,
    source_row   INTEGER,
    raw_category TEXT,
    raw_program  TEXT,
    reason       TEXT,
    ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging_seats (
    id          SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    raw_row     TEXT NOT NULL,
    loaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed   BOOLEAN DEFAULT FALSE,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS seats_ingest_log (
    id             SERIAL PRIMARY KEY,
    source_file    TEXT NOT NULL,
    rows_read      INTEGER,
    rows_inserted  INTEGER,
    rows_skipped   INTEGER,
    rows_duplicate INTEGER DEFAULT 0,
    rows_failed    INTEGER,
    ingested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seats_ingest_errors (
    id                  SERIAL PRIMARY KEY,
    source_file         TEXT NOT NULL,
    source_page         INTEGER,
    institution_code    TEXT,
    choice_code         TEXT,
    raw_allocation_type TEXT,
    raw_category        TEXT,
    reason              TEXT,
    ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- ============================================================
-- PRECOMPUTED PUBLIC RUNTIME DATA
-- These tables contain derived data used by the candidate site.
-- Raw cutoffs/seats remain the source of truth.
-- ============================================================

CREATE TABLE IF NOT EXISTS cutoff_trend_points (
    program_family TEXT NOT NULL,
    institution_code TEXT NOT NULL,
    program_id INTEGER NOT NULL,
    base_category TEXT NOT NULL,
    is_ladies BOOLEAN NOT NULL DEFAULT FALSE,
    section_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    round INTEGER NOT NULL,
    closing_percentile REAL NOT NULL,
    closing_rank INTEGER,
    PRIMARY KEY (program_family, institution_code, program_id, base_category,
                 is_ladies, section_code, year, round)
);

CREATE INDEX IF NOT EXISTS idx_cutoff_trend_lookup
    ON cutoff_trend_points(program_family, institution_code, base_category,
                           is_ladies, section_code, year, round);

CREATE TABLE IF NOT EXISTS cutoff_college_year_summary (
    program_family TEXT NOT NULL,
    institution_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    low_percentile REAL NOT NULL,
    high_percentile REAL NOT NULL,
    low_rank INTEGER,
    PRIMARY KEY (program_family, institution_code, year)
);

CREATE INDEX IF NOT EXISTS idx_cutoff_summary_lookup
    ON cutoff_college_year_summary(program_family, institution_code, year);

CREATE TABLE IF NOT EXISTS cutoff_filter_options (
    program_family TEXT NOT NULL,
    institution_code TEXT NOT NULL,
    is_ladies BOOLEAN NOT NULL DEFAULT FALSE,
    year INTEGER NOT NULL,
    base_category TEXT NOT NULL,
    section_code TEXT NOT NULL,
    PRIMARY KEY (program_family, institution_code, is_ladies, year,
                 base_category, section_code)
);

CREATE INDEX IF NOT EXISTS idx_cutoff_options_lookup
    ON cutoff_filter_options(program_family, institution_code, is_ladies,
                             year, base_category, section_code);

CREATE TABLE IF NOT EXISTS seat_matrix_runtime (
    program_family TEXT NOT NULL,
    institution_code TEXT NOT NULL,
    capture_year INTEGER NOT NULL,
    choice_code TEXT NOT NULL,
    allocation_lane TEXT NOT NULL,
    base_category TEXT NOT NULL,
    gender_g INTEGER,
    gender_l INTEGER,
    category_total INTEGER,
    is_total BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (program_family, institution_code, capture_year, choice_code,
                 allocation_lane, base_category, is_total)
);

CREATE INDEX IF NOT EXISTS idx_seat_runtime_lookup
    ON seat_matrix_runtime(program_family, institution_code, capture_year,
                           choice_code, allocation_lane);

CREATE TABLE IF NOT EXISTS derived_data_build_jobs (id BIGSERIAL PRIMARY KEY, course_family TEXT, status TEXT NOT NULL DEFAULT 'QUEUED', progress INTEGER NOT NULL DEFAULT 0, message TEXT, started_at TIMESTAMP, finished_at TIMESTAMP, created_by BIGINT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_derived_build_jobs_created ON derived_data_build_jobs(created_at DESC);
