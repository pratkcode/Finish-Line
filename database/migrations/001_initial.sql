-- 001: initial schema (single-department catalog, degree requirements, planning sessions).
-- Existing databases created from the old schema.sql are recorded as having applied this.



CREATE TABLE universities (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE programs (
    id            SERIAL PRIMARY KEY,
    university_id INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    slug          TEXT NOT NULL UNIQUE,             -- URL id, e.g. 'umd-information-science'
    name          TEXT NOT NULL,
    UNIQUE (university_id, name)
);

CREATE TABLE courses (
    id                     SERIAL PRIMARY KEY,
    university_id          INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    code                   TEXT NOT NULL,           -- e.g. 'INST326'
    subject                TEXT GENERATED ALWAYS AS (substring(code from 1 for 4)) STORED,
    number                 INTEGER GENERATED ALWAYS AS (substring(code from 5 for 3)::integer) STORED,
    name                   TEXT NOT NULL,
    credits_min            INTEGER NOT NULL CHECK (credits_min >= 0),
    credits_max            INTEGER NOT NULL CHECK (credits_max >= credits_min),
    description            TEXT,
    prerequisite_text      TEXT,                    -- official catalog wording
    corequisite_text       TEXT,                    -- official catalog wording
    -- true when prerequisite_groups fully capture prerequisite_text and
    -- corequisite_text; false when part of it (placement, permission, etc.)
    -- could not be represented as courses.
    prerequisites_complete BOOLEAN NOT NULL DEFAULT TRUE,
    gen_ed_text            TEXT,                    -- as listed on Testudo, e.g. 'DSHS or DSNS'
    restriction_text       TEXT,                    -- official catalog wording
    credit_only_granted_for TEXT,                   -- official catalog wording
    UNIQUE (university_id, code)
);

-- A course's prerequisites are a set of groups. Every group must be
-- satisfied; within a group, any one of its option courses satisfies it.
--   INST346: (INST201 or INST301) and (INST326) and (INST327)
CREATE TABLE prerequisite_groups (
    id        SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    timing    TEXT NOT NULL DEFAULT 'before'
              CHECK (timing IN ('before', 'before_or_concurrent', 'concurrent')),
    min_grade TEXT                                  -- e.g. 'C-'; NULL if none stated
);

CREATE TABLE prerequisite_options (
    group_id  INTEGER NOT NULL REFERENCES prerequisite_groups(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, course_id)
);

CREATE INDEX ON prerequisite_groups (course_id);
CREATE INDEX ON prerequisite_options (course_id);

-- General Education tags carried by a course (FSAW, DSHS, SCIS, DVUP, ...).
CREATE TABLE course_gen_ed (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    PRIMARY KEY (course_id, tag)
);

-- Enrollment restrictions, structured from courses.restriction_text.
CREATE TABLE course_restrictions (
    course_id          INTEGER PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE,
    min_credits_earned INTEGER CHECK (min_credits_earned > 0),
    programs           TEXT[],          -- must be in one of these programs; NULL = any
    other_conditions   TEXT,            -- not modeled (permission, campus, ...)
    -- true when other_conditions mean the course isn't generally open, so the
    -- planner won't choose it as an elective.
    avoid_in_plan      BOOLEAN NOT NULL DEFAULT FALSE
);

-- Pairs of courses that limit each other:
--   credit_overlap: credit is only granted for one of them (stored both ways)
--   not_after:      course_id can't be taken after completing other_course_id
CREATE TABLE course_exclusions (
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    other_course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('credit_overlap', 'not_after')),
    PRIMARY KEY (course_id, other_course_id, kind),
    CHECK (course_id <> other_course_id)
);

-- Degree requirements form a tree. A top-level requirement belongs either to
-- a university (applies to all its programs) or to one program.
-- See database/data/requirements.json for what each rule means.
CREATE TABLE requirements (
    id               SERIAL PRIMARY KEY,
    key              TEXT NOT NULL UNIQUE,          -- stable id, e.g. 'infosci.core'
    parent_id        INTEGER REFERENCES requirements(id) ON DELETE CASCADE,
    university_id    INTEGER REFERENCES universities(id) ON DELETE CASCADE,
    program_id       INTEGER REFERENCES programs(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    description      TEXT,
    category         TEXT NOT NULL CHECK (category IN (
                         'university', 'general_education', 'major',
                         'major_benchmark', 'major_core', 'major_elective', 'major_cognate')),
    rule             TEXT NOT NULL CHECK (rule IN (
                         'all_courses', 'min_courses', 'min_credits',
                         'all_children', 'any_child', 'course_list', 'not_tracked')),
    min_courses      INTEGER CHECK (min_courses > 0),
    min_credits      INTEGER CHECK (min_credits > 0),
    min_grade        TEXT,                          -- e.g. 'C-'; NULL = any passing grade
    -- Within one allocation group a course counts toward only one requirement.
    allocation_group TEXT,
    optional         BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    source_url       TEXT,
    CHECK ((parent_id IS NULL) = ((university_id IS NULL) <> (program_id IS NULL))),
    CHECK (rule <> 'min_courses' OR min_courses IS NOT NULL),
    CHECK (rule <> 'min_credits' OR min_credits IS NOT NULL)
);

-- Specific courses that satisfy a requirement.
CREATE TABLE requirement_courses (
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    course_id      INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    PRIMARY KEY (requirement_id, course_id)
);

-- Rules that match many courses. A course matches a filter when it matches
-- every non-NULL column; it is eligible when it matches any filter.
CREATE TABLE requirement_course_filters (
    id             SERIAL PRIMARY KEY,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    subject        TEXT,                            -- e.g. 'INST'
    min_number     INTEGER,                         -- e.g. 300
    max_number     INTEGER,                         -- e.g. 499
    gen_ed         TEXT,                            -- e.g. 'DSHS'
    CHECK (COALESCE(subject, min_number::text, max_number::text, gen_ed) IS NOT NULL)
);

CREATE INDEX ON requirements (parent_id);
CREATE INDEX ON requirement_courses (course_id);
CREATE INDEX ON course_gen_ed (tag);

-- A student's temporary planning session (no accounts yet). The browser
-- keeps the session id; anyone with the id can read and edit the session.
CREATE TABLE planning_sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id           INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    -- Credit total the student typed in. Kept for comparison only; the
    -- completed credit total is always calculated from session_courses.
    reported_credits     INTEGER CHECK (reported_credits BETWEEN 0 AND 300),
    current_term         TEXT CHECK (current_term ~ '^(Spring|Summer|Fall|Winter) [0-9]{4}$'),
    max_credits_per_term INTEGER NOT NULL DEFAULT 15 CHECK (max_credits_per_term BETWEEN 1 AND 30),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Courses the student has completed.
CREATE TABLE session_courses (
    session_id UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    course_id  INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    credits    INTEGER NOT NULL CHECK (credits >= 0),  -- matters for variable-credit courses
    grade      TEXT,                                   -- optional: 'A+' ... 'F', 'P'
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, course_id)
);

-- The student's own changes to the generated graduation plan.
--   term set:     the course is placed in that semester (added or moved)
--   removed true: the course is left out of the plan
CREATE TABLE plan_overrides (
    session_id UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    course_id  INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    term       TEXT CHECK (term ~ '^(Spring|Fall) [0-9]{4}$'),
    removed    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (session_id, course_id),
    CHECK ((term IS NULL) = removed)
);
