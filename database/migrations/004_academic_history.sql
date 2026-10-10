-- 004: academic history, transfer credit, verified requirement fulfillments,
-- flexible plan timelines, and course offering history.
--
-- Only adds tables and columns (and widens one check). Existing completed
-- courses become "completed, semester not recorded".

-- Plan settings on the student's session.
ALTER TABLE planning_sessions
    -- First semester of the future plan (defaults to the term after current_term).
    ADD COLUMN plan_start_term TEXT CHECK (plan_start_term ~ '^(Spring|Summer|Fall) [0-9]{4}$'),
    ADD COLUMN target_graduation_term TEXT
        CHECK (target_graduation_term ~ '^(Spring|Summer|Fall|Winter) [0-9]{4}$'),
    -- As the student describes it; informational only.
    ADD COLUMN academic_standing TEXT CHECK (length(academic_standing) <= 100),
    -- Whether recommendations may use Summer terms, and how many credits there.
    ADD COLUMN include_summer BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN max_summer_credits INTEGER CHECK (max_summer_credits BETWEEN 1 AND 30);

-- A semester the student attended, at UMD or another institution.
CREATE TABLE academic_terms (
    id          SERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    term        TEXT NOT NULL CHECK (term ~ '^(Spring|Summer|Fall|Winter) [0-9]{4}$'),
    institution TEXT NOT NULL CHECK (length(institution) BETWEEN 1 AND 200),
    at_umd      BOOLEAN NOT NULL,         -- true for University of Maryland, College Park
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, institution, term)
);

-- UMD courses: which semester, and whether still in progress. In-progress
-- courses are not completed: they don't count toward requirements yet.
ALTER TABLE session_courses
    ADD COLUMN academic_term_id INTEGER REFERENCES academic_terms(id) ON DELETE CASCADE,
    ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'in_progress')),
    ADD CONSTRAINT in_progress_has_no_grade CHECK (status = 'completed' OR grade IS NULL);

-- Coursework and credit from other institutions (or exams).
--   kind 'course':  an external course (code and/or title)
--   kind 'credits': credit that doesn't map to one course (e.g. a block of elective credit)
-- verification:
--   student_reported  entered by the student; shown, but never counted toward requirements
--   umd_verified      the student confirms UMD has evaluated it (e.g. on their UMD transcript)
-- A verified entry with an equivalent UMD course counts as that course; a verified
-- entry without one counts toward total credits only.
CREATE TABLE transfer_credits (
    id                   SERIAL PRIMARY KEY,
    session_id           UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    academic_term_id     INTEGER REFERENCES academic_terms(id) ON DELETE CASCADE,
    institution          TEXT NOT NULL CHECK (length(institution) BETWEEN 1 AND 200),
    kind                 TEXT NOT NULL CHECK (kind IN ('course', 'credits')),
    external_code        TEXT CHECK (length(external_code) <= 30),
    title                TEXT CHECK (length(title) <= 200),
    credits              INTEGER NOT NULL CHECK (credits BETWEEN 0 AND 200),
    grade                TEXT CHECK (length(grade) <= 10),
    status               TEXT NOT NULL DEFAULT 'completed'
                         CHECK (status IN ('completed', 'in_progress')),
    equivalent_course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    verification         TEXT NOT NULL DEFAULT 'student_reported'
                         CHECK (verification IN ('student_reported', 'umd_verified')),
    verification_note    TEXT CHECK (length(verification_note) <= 500),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kind = 'credits' OR external_code IS NOT NULL OR title IS NOT NULL),
    CHECK (kind = 'course' OR equivalent_course_id IS NULL)
);
CREATE INDEX ON transfer_credits (session_id);

-- Requirements met some other way than a course in the plan: a transfer
-- evaluation, an exam, a waiver, an approved substitution, an associate degree.
-- Only umd_verified and approved_exception entries count.
CREATE TABLE requirement_fulfillments (
    id                 SERIAL PRIMARY KEY,
    session_id         UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    requirement_key    TEXT NOT NULL,     -- requirements.key (requirements are rebuilt by syncs)
    method             TEXT NOT NULL CHECK (method IN ('transfer_credit', 'exam_credit', 'waiver',
                                            'substitution', 'associate_degree', 'other')),
    verification       TEXT NOT NULL DEFAULT 'student_reported'
                       CHECK (verification IN ('student_reported', 'umd_verified',
                                               'approved_exception')),
    note               TEXT CHECK (length(note) <= 500),
    transfer_credit_id INTEGER REFERENCES transfer_credits(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, requirement_key)
);

-- Plans may use Summer terms now.
ALTER TABLE planned_courses DROP CONSTRAINT planned_courses_term_check;
ALTER TABLE planned_courses
    ADD CONSTRAINT planned_courses_term_check CHECK (term ~ '^(Spring|Summer|Fall) [0-9]{4}$');

-- Terms in which a course had sections on Testudo (verified offering history),
-- and which terms were checked, so "not offered" can be told from "no data".
CREATE TABLE offering_terms (
    term TEXT PRIMARY KEY CHECK (term ~ '^(Spring|Summer|Fall|Winter) [0-9]{4}$')
);
CREATE TABLE course_offerings (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    term      TEXT NOT NULL REFERENCES offering_terms(term) ON DELETE CASCADE,
    PRIMARY KEY (course_id, term)
);
