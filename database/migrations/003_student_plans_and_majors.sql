-- 003: student-owned semester plans, and majors with or without verified requirements.
--
-- Before: the graduation plan was regenerated on every request, and a
-- student's edits were stored as "overrides" on top of it, so removing a
-- course just made the planner refill the semester. Now the plan is the
-- student's own list of courses per semester; generating a recommendation is
-- optional and only saves anything when the student accepts it.

-- Majors: which ones have verified requirement data in Finish Line.
ALTER TABLE programs
    ADD COLUMN requirements_status TEXT NOT NULL DEFAULT 'not_available'
        CHECK (requirements_status IN ('verified', 'not_available')),
    ADD COLUMN catalog_url TEXT;
UPDATE programs SET requirements_status = 'verified'
    WHERE id IN (SELECT program_id FROM requirements WHERE program_id IS NOT NULL);

-- The student's saved semester plan. One row per course, so a course can't be
-- planned twice; credits are stored per row (variable-credit courses).
CREATE TABLE planned_courses (
    session_id UUID NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    course_id  INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    term       TEXT NOT NULL CHECK (term ~ '^(Spring|Fall) [0-9]{4}$'),
    credits    INTEGER NOT NULL CHECK (credits >= 0),
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, course_id)
);
CREATE INDEX ON planned_courses (session_id, term);

-- Keep what students had placed: each placed course becomes a planned course.
INSERT INTO planned_courses (session_id, course_id, term, credits)
SELECT o.session_id, o.course_id, o.term, c.credits_min
FROM plan_overrides o JOIN courses c ON c.id = o.course_id
WHERE o.term IS NOT NULL;

DROP TABLE plan_overrides;
