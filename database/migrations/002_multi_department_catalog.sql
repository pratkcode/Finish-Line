-- 002: catalog across all UMD departments.
--
-- Adds departments, provenance and verification status for course data, and
-- conditional Gen Ed tags. Only adds tables and columns; existing rows,
-- planning sessions and completed courses are untouched.

CREATE TABLE departments (
    university_id INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    code          TEXT NOT NULL,              -- e.g. 'MATH'
    name          TEXT NOT NULL,              -- e.g. 'Mathematics'
    PRIMARY KEY (university_id, code)
);

-- Where each course record came from, and how far its details are verified.
ALTER TABLE courses
    ADD COLUMN catalog_year           TEXT,       -- e.g. '2026-2027'
    ADD COLUMN source_url             TEXT,       -- official catalog page
    -- false when a later catalog import no longer lists the course. Such
    -- courses are kept (students may have completed them) but never suggested.
    ADD COLUMN in_current_catalog     BOOLEAN NOT NULL DEFAULT TRUE,
    -- How the structured prerequisites were produced:
    --   curated      reviewed by hand against the catalog text
    --   parsed       the whole catalog text matched a strict pattern
    --   partial      the course part was parsed; the text also allows something
    --                that isn't a course (permission, placement, ...)
    --   unstructured the text couldn't be parsed; only the wording is available
    --   none         the catalog lists no prerequisite
    ADD COLUMN prerequisite_status    TEXT NOT NULL DEFAULT 'none'
        CHECK (prerequisite_status IN ('curated', 'parsed', 'partial', 'unstructured', 'none')),
    -- Gen Ed tags come from Testudo listings for recent terms:
    --   verified     tags found; see course_gen_ed
    --   none_found   not in any listing for those terms (may still be approved)
    ADD COLUMN gen_ed_status          TEXT NOT NULL DEFAULT 'none_found'
        CHECK (gen_ed_status IN ('verified', 'none_found')),
    ADD COLUMN gen_ed_term            TEXT,       -- Testudo term the tags were read from
    -- Further official catalog details, as written.
    ADD COLUMN formerly               TEXT,
    ADD COLUMN cross_listed_with      TEXT,
    ADD COLUMN jointly_offered_with   TEXT,
    ADD COLUMN repeatable_to          TEXT,
    ADD COLUMN recommended            TEXT,
    ADD COLUMN additional_information TEXT;

-- Existing rows came from the 2026-2027 catalog with hand-curated prerequisites.
UPDATE courses SET catalog_year = '2026-2027';
UPDATE courses SET prerequisite_status = 'curated'
    WHERE id IN (SELECT course_id FROM prerequisite_groups) OR subject = 'INST';
UPDATE courses SET gen_ed_status = 'verified'
    WHERE id IN (SELECT course_id FROM course_gen_ed);

-- A tag with a condition (e.g. DSNL only "if taken with BSCI161") is stored
-- but not counted toward requirements until the condition can be checked.
ALTER TABLE course_gen_ed
    ADD COLUMN condition_text TEXT;

-- How a restriction row was produced: hand-curated, or parsed from text that
-- matched a strict pattern ('parsed'), or kept as text only ('text_only').
ALTER TABLE course_restrictions
    ADD COLUMN source TEXT NOT NULL DEFAULT 'curated'
        CHECK (source IN ('curated', 'parsed', 'text_only'));

CREATE INDEX ON courses (subject);
CREATE INDEX ON courses (in_current_catalog);
