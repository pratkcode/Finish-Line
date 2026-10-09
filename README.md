# Finish Line

*Your degree. Your plan. Your finish line.*

**A degree planner for UMD Information Science students.** Enter the courses you've completed. Finish Line shows which degree requirements are done, what's left, which courses you can take next, and a semester-by-semester path to the earliest graduation, which you can rearrange with what-ifs.

> **Finish Line is a planning tool, not an official UMD degree audit.** Its data comes from the public UMD catalog and Schedule of Classes, and every generated plan is a recommendation. Students should confirm plans with an academic advisor.

![Dashboard](docs/screenshots/dashboard.png)

| Graduation plan | Degree progress | Course dependencies |
| --- | --- | --- |
| ![Graduation plan](docs/screenshots/graduation-plan.png) | ![Degree progress](docs/screenshots/degree-progress.png) | ![Course dependencies](docs/screenshots/course-dependencies.png) |

---

## Features

- **Dashboard:** the student's program, credits (61 / 120), projected graduation, requirement completion, next semester's courses, and links to every tool.
- **Degree progress:** every university, General Education, and major requirement, marked complete, in progress, not started, or not tracked yet. Each remaining requirement lists the courses that can still fill it, with their prerequisite status.
- **Prerequisites and dependencies:** for any course, whether the student can take it now, which prerequisites are missing, the full prerequisite chain, and which courses it unlocks.
- **Graduation plan:** an automatically generated semester-by-semester plan. It respects prerequisites, the student's credit limit, and catalog restrictions such as "must have earned 90 credits".
- **What-if planning:** move, add, or remove courses. Everything that depends on them is re-planned, the projected graduation updates, and broken rules show as warnings. Changes are previewed until you save them.
- **Course search:** all 106 courses in the dataset by code or name, with Gen Ed tags, restrictions, and prerequisites.
- **No accounts:** a student's profile is a planning session stored in PostgreSQL and remembered by the browser.

## Technology

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.13, FastAPI, Pydantic, psycopg 3 with a connection pool |
| Database | PostgreSQL 17 |
| Tests | pytest (126 tests): pure unit tests of the engines plus API tests against the seeded database |

## Architecture

```
 Browser (Next.js / React)
 ─────────────────────────────────────────────────────────────────────
  Dashboard · Graduation Plan · Degree Progress · Courses · Profile
  Display and editing only. No degree or prerequisite logic lives here.
                               │
                               │  JSON over HTTP (lib/api.ts)
                               ▼
 FastAPI (backend/app)
 ─────────────────────────────────────────────────────────────────────
  Routes      courses · requirements · sessions · degree_progress
              eligibility · graduation_plan · dashboard
                               │
  Services    evaluator.py      requirement rules  → completion status
  (pure       prerequisites.py  prerequisite graph → eligibility, chains
   Python)    planner.py        choose courses → topological schedule
              restrictions.py   program limits, credit overlaps, standing
                               │
                               │  SQL (psycopg pool)
                               ▼
 PostgreSQL
 ─────────────────────────────────────────────────────────────────────
  Catalog      courses · prerequisite_groups · prerequisite_options
               course_gen_ed · course_restrictions · course_exclusions
  Degree       universities · programs · requirements
               requirement_courses · requirement_course_filters
  Students     planning_sessions · session_courses · plan_overrides
                               ▲
                               │  generated seed.sql
 database/build_seed.py ── validates ── database/data/*.json (curated from the UMD catalog)
```

Design principles:

- **Degree logic lives in the database.** Requirements, prerequisites and restrictions are rows. The Python engines evaluate whatever rules they're given; there is no `if course == "INST201"` anywhere. Adding a program means adding data.
- **Engines are pure functions.** `evaluator`, `prerequisites` and `planner` take plain data and return plain data. Routes load from the database and hand it over, so the logic is unit-tested on small made-up degrees.
- **The frontend only displays.** It never decides whether a requirement is met or a course is available. It asks the API.

## Project structure

```
backend/
  app/
    main.py              app setup, CORS, database-outage handler (503)
    db.py, config.py     connection pool, settings from .env
    courses.py           course search, detail, prerequisites, dependents, prerequisite tree
    requirements.py      programs, requirement tree, progress for a course list
    sessions.py          planning session (profile + completed courses)
    degree_progress.py   completed / remaining requirements for a session
    eligibility.py       available vs. blocked remaining courses
    graduation_plan.py   generated plan, what-if preview, saved changes
    dashboard.py         one-call dashboard summary
    evaluator.py         requirement rule engine          (pure)
    prerequisites.py     prerequisite graph and checks    (pure)
    planner.py           course selection and scheduling  (pure)
    restrictions.py      enrollment rules                 (pure)
  tests/                 pytest suite
database/
  schema.sql             all tables (re-runnable)
  data/*.json            curated catalog data
  build_seed.py          validates the JSON and generates seed.sql
  seed.sql               generated
frontend/
  src/app/               pages: /, /dashboard, /graduation-plan, /progress, /courses, /requirements, /profile
  src/components/        page components; plan/ (timeline), ui/ (states, progress bar)
  src/lib/               API client, session storage, shared hooks
docs/screenshots/
```

## Database design

```
universities ─┬─< programs ─────< planning_sessions ─┬─< session_courses >── courses
              │                                       └─< plan_overrides  >── courses
              ├─< courses ─┬─< prerequisite_groups ─< prerequisite_options >── courses
              │            ├─< course_gen_ed
              │            ├── course_restrictions
              │            └─< course_exclusions >── courses
              └─< requirements (tree via parent_id; also owned by programs)
                     ├─< requirement_courses >── courses
                     └─< requirement_course_filters
```

**Prerequisites** are *groups of alternatives*. Every group must be met, and any one option meets a group:

```
INST346  =  (INST201 or INST301)  AND  (INST326)  AND  (INST327)
            └──── group 1 ───────┘    └ group 2 ┘    └ group 3 ┘
```

Each group also stores a minimum grade (e.g. C-) and a timing: completed before, before or in the same semester, or a corequisite taken in the same semester.

**Requirements** form a tree. Each node has a `rule`:

| Rule | Meaning | Example |
| --- | --- | --- |
| `all_courses` | every listed course | Major core (10 courses) |
| `min_courses` | N courses from a set | Gen Ed Humanities: 2 courses tagged DSHU |
| `min_credits` | N credits from a set | Major electives: 15 credits of INST 300–499 |
| `all_children` / `any_child` | all / one of the child requirements | Diversity: 2 UPS courses, or 1 UPS + 1 Cultural Competence |
| `course_list` | a list with no stated count (shown, not scored) | Some cognate areas |
| `not_tracked` | can't be checked from a course list | GPA, residency |

A requirement's courses come either from an explicit list (`requirement_courses`) or from patterns (`requirement_course_filters`: subject, number range, Gen Ed tag). An **allocation group** controls double counting: inside one group a course counts once (a core course isn't also an elective), but across groups it can count again where UMD allows it (INST201 counts for the major core *and* Gen Ed).

**Restrictions** are structured from the catalog text: minimum earned credits (INST490: 90), allowed programs, "credit only granted for" pairs (INST201/INST301), and "can't take after" (INST123 after INST327).

## How the engines work

### Requirement evaluation (`evaluator.py`)

The evaluator walks the requirement tree, assigning the student's courses to leaf requirements:
- **Grade minimums:** a course only counts where it meets the requirement's minimum grade.
- **Allocation groups:** within a group, a course counts toward one requirement only.
- **Least flexible first:** the courses that fit the fewest requirements are assigned first, so a course that could fill several isn't used up where another would do.
- **"One of" requirements:** each option is tried on its own copy of the assignments, and the best one is kept.

### Prerequisites (`prerequisites.py`)

For each course and student, the prerequisite service returns:
- **Status:** available, available with a same-semester course, blocked, or completed.
- **Each group's state:** met, can be met in the same semester, or missing.
- **What to complete first:** an ordered list, worked out recursively. Where a group allows alternatives, it picks the option that needs the fewest extra courses (memoized, with a guard against circular prerequisites).

### Scheduling (`planner.py`)

The planner works in two phases.

**1. Choose courses (what to take)**
- **Required courses first:** every course on an "all of these" list.
- **Then each remaining requirement, in degree order:** it picks one course, preferring one that also fills other remaining requirements, then the fewest extra prerequisites, then fixed-credit courses.
- **Re-evaluate after every pick,** so a course that fills two requirements isn't doubled up.
- **Add prerequisite chains.** Courses the student can't take (other programs, credit overlaps, permission-only) are skipped.
- **Fill the gaps:** a requirement with no suitable catalog course gets a labeled "Choose a course" slot, and general-elective slots close any gap to 120 credits.

**2. Schedule (when to take it)**
- **Build a directed graph:** chosen courses are nodes, and each unmet prerequisite group adds an edge from one planned option to the course.
- **Topological sort:** Kahn's algorithm orders the graph and detects cycles.
- **Critical path:** each course gets a priority equal to the length of the longest chain that starts at it.
- **List scheduling:** each Fall and Spring takes ready courses up to the credit limit, longest chain first and then required before elective. A course is ready when its "before" prerequisites are in earlier terms, its same-semester prerequisites are in this term or earlier, and the student has the earned credits its restriction needs.
- **Earliest graduation:** the plan is compared with a lower bound, `max(⌈credits ÷ limit⌉, longest chain)`. When they match, the date is reported as the earliest possible under the stated assumptions. Otherwise the note explains the delay, e.g. credit standing.

**What-if editing** adds *overrides* on top:
- **Placed courses** (moved or added) are fixed in their semester.
- **Removed courses** are never chosen, and the planner substitutes where a requirement still needs a course.
- **Everything else** is re-planned by the same algorithm.
- **Validation:** a final pass reports anything a placed course breaks (missing prerequisites, credit limit, credit standing) as warnings, instead of hiding it.

## Data sources and accuracy

- **Courses and prerequisites:** UMD Undergraduate Catalog 2026–2027. This covers all 83 undergraduate INST courses and the 23 other courses their prerequisites name. Prerequisite rules were curated by hand from the official text, with the text kept for display.
- **Major requirements:** the catalog, plus the InfoSci program site for elective rules and cognate course lists.
- **General Education and university rules:** the catalog.
- **Gen Ed tags:** Testudo's Schedule of Classes (three recent terms).
- **Validation:** `build_seed.py` refuses to build if a prerequisite, restriction number, program name or course code doesn't appear in the official text.
- **Nothing is guessed.** Rules that can't be expressed as courses are kept as text and flagged rather than invented, e.g. "MATH115 or higher", math placement, permission. That covers 15 INST courses, and the UI points to the official wording.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | API and database status |
| GET | `/api/courses?search=` | Search courses by code or name |
| GET | `/api/courses/{code}` | Course detail: Gen Ed, restrictions, prerequisites |
| GET | `/api/courses/{code}/prerequisites` | Prerequisite groups |
| GET | `/api/courses/{code}/prerequisite-tree` | Every level of prerequisites |
| GET | `/api/courses/{code}/dependents` | Courses it unlocks |
| GET | `/api/programs` | Programs |
| GET | `/api/programs/{slug}/requirements` | Requirement tree with eligible courses |
| POST | `/api/programs/{slug}/progress` | Evaluate any course list (stateless) |
| POST | `/api/sessions` | Create a planning session |
| GET / PATCH / DELETE | `/api/sessions/{id}` | Profile: program, semester, credit limit, reported credits |
| GET / POST | `/api/sessions/{id}/courses` | Completed courses |
| PATCH / DELETE | `/api/sessions/{id}/courses/{code}` | Change grade or credits, or remove |
| GET | `/api/sessions/{id}/summary` | Dashboard summary |
| GET | `/api/sessions/{id}/progress` | Completed / remaining requirements and credits |
| GET | `/api/sessions/{id}/eligibility` | Available vs. blocked remaining courses |
| GET | `/api/sessions/{id}/eligibility/{code}` | One course's prerequisite status |
| GET | `/api/sessions/{id}/plan` | Generated plan (with saved changes) |
| POST | `/api/sessions/{id}/plan/preview` | What-if preview, not saved |
| PUT | `/api/sessions/{id}/plan/overrides` | Save plan changes |

Interactive docs: http://localhost:8000/docs. Errors use FastAPI's `{"detail": "..."}` shape. The API returns 404 for unknown courses or sessions, 409 for conflicts, 422 for invalid input, and 503 when the database is down.

## Running locally

**Prerequisites:** Node.js 20+, Python 3.11+, PostgreSQL 15+. On macOS: `brew install postgresql@17 && brew services start postgresql@17`.

```bash
# 1. Database
createdb finish_line
psql -d finish_line -f database/schema.sql
psql -d finish_line -f database/seed.sql

# 2. Backend → http://localhost:8000
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # DATABASE_URL, CORS_ORIGINS
uvicorn app.main:app --reload --port 8000

# 3. Frontend → http://localhost:3000
cd frontend
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_URL
npm run dev
```

Open http://localhost:3000, choose **Start Planning**, add a few completed courses, then open the **Dashboard** and the **Graduation Plan**.

To change catalog or degree data, edit `database/data/*.json`, then run `python3 database/build_seed.py` and re-run both SQL files. Re-running `schema.sql` resets all planning sessions.

### Tests

```bash
cd backend && pytest
```

The suite has 126 tests. The engine tests use small made-up degrees, and the API tests run against the seeded database.

| Area | Where |
| --- | --- |
| Requirement completion, grade minimums, double counting | `test_evaluator.py`, `test_degree_progress.py` |
| Missing requirements and course suggestions | `test_degree_progress.py`, `test_requirements_api.py` |
| Prerequisites: none, one, several, alternatives, corequisites, cycles | `test_prerequisites.py` |
| Multi-level dependency chains | `test_prerequisites.py`, `test_planner.py` |
| Credit limits (several limits, oversized courses, pins over the limit) | `test_planner.py` |
| Schedule generation and what-if overrides | `test_planner.py` |
| Earliest graduation (credit-bound, chain-bound, standing-delayed) | `test_planner.py` |
| Sessions, dashboard, search, 503 handling | `test_sessions_api.py`, `test_dashboard.py`, `test_api.py` |

## Known limitations

- **Scope:** one university and one program. The schema supports more, but only UMD Information Science data exists.
- **Course offerings and seats aren't known.** The planner assumes every course runs every Fall and Spring, and doesn't use Winter or Summer.
- **Limited catalog:** only 106 courses are in the database. Gen Ed areas without a matching course in the database (writing, oral communication, lab science) become 3-credit "Choose a course" slots.
- **Not checked:** GPA, residency, permissions, and "or higher" math prerequisites are shown but not enforced.
- **Greedy, not optimal:** course choice is greedy. The schedule's length is checked against a lower bound, but the planner isn't an optimal solver.
- **No accounts:** anyone holding a session ID can edit that plan, and sessions don't expire. There's no rate limiting.

## Future improvements

- **Offering-aware scheduling:** import historical Testudo offerings so courses are only planned in terms they're usually taught, with Summer and Winter as options.
- **Full catalog import:** an automated, repeatable catalog and Schedule of Classes import, covering all departments and every year's catalog.
- **Accounts:** sign-in so plans persist across devices, with session expiry and rate limiting.
- **More programs:** start with the other College of Information majors, using the same tables.
- **Smarter optimization:** an ILP/CP-SAT formulation, so "earliest graduation" is provably optimal and can balance workload or preferred courses.
- **Advisor sharing:** read-only links to send a plan to an advisor.
- **CI:** GitHub Actions running pytest against a PostgreSQL service container, plus frontend lint and build.
