"use client";

import { useEffect, useRef, useState } from "react";
import CourseDetail from "@/components/CourseDetail";
import { ErrorState } from "@/components/ui/States";
import {
  formatCredits,
  getCourse,
  getDepartments,
  getDependents,
  getPrerequisiteTree,
  getSession,
  type CourseDetail as Course,
  type Department,
  type Dependent,
  type PrerequisiteTree,
} from "@/lib/api";
import { readSessionId } from "@/lib/session";
import { useCourseSearch } from "@/lib/useCourseSearch";

export type SelectedCourse = { course: Course; dependents: Dependent[]; tree: PrerequisiteTree };

export default function CourseBrowser() {
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const {
    results: courses,
    total,
    error: listError,
  } = useCourseSearch(search, { allWhenEmpty: true, department });
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedCourse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const detailRef = useRef<HTMLElement>(null);

  // Open the course in the URL (?code=INST326), and note the student's
  // completed courses so the dependency view can check them off.
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (code) queueMicrotask(() => setSelectedCode(code.toUpperCase()));
    getDepartments()
      .then(setDepartments)
      .catch(() => {});
    const id = readSessionId();
    if (id) {
      getSession(id)
        .then((s) => setCompleted(new Set(s.courses.map((c) => c.code))))
        .catch(() => {});
    }
  }, []);

  function selectCourse(code: string) {
    setSelectedCode(code);
    window.history.replaceState(null, "", `?code=${code}`);
    // On narrow screens the details sit below the list, so bring them into view.
    if (window.matchMedia("(max-width: 767px)").matches) {
      detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // Load the selected course, what it requires, and what it unlocks.
  useEffect(() => {
    if (!selectedCode) return;
    const controller = new AbortController();
    Promise.all([
      getCourse(selectedCode, controller.signal),
      getDependents(selectedCode, controller.signal),
      getPrerequisiteTree(selectedCode, controller.signal),
    ])
      .then(([course, dependents, tree]) => {
        setSelected({ course, dependents, tree });
        setDetailError(null);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setDetailError(err.message);
      });
    return () => controller.abort();
  }, [selectedCode]);

  return (
    <div className="grid gap-6 md:grid-cols-[320px_1fr]">
      <section className="flex flex-col">
        <label htmlFor="course-search" className="sr-only">
          Search courses
        </label>
        <input
          id="course-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by code or name"
          className="w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm focus:border-red-700 focus:ring-1 focus:ring-red-700 focus:outline-none"
        />
        <label htmlFor="course-department" className="sr-only">
          Department
        </label>
        <select
          id="course-department"
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          className="mt-2 w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm focus:border-red-700 focus:outline-none"
        >
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d.code} value={d.code}>
              {d.code}: {d.name} ({d.course_count})
            </option>
          ))}
        </select>

        <p className="mt-3 text-xs text-slate-500" aria-live="polite">
          {courses === null
            ? listError
              ? "Search unavailable"
              : "Loading…"
            : courses.length < total
              ? `Showing ${courses.length} of ${total.toLocaleString()} courses. Search or pick a department to narrow it down.`
              : `${total.toLocaleString()} ${total === 1 ? "course" : "courses"}`}
        </p>

        {listError ? (
          <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{listError}</p>
        ) : (
          <ul className="mt-2 max-h-80 overflow-y-auto rounded-xl border border-slate-200 bg-surface md:max-h-[calc(100vh-15rem)]">
            {courses === null &&
              [0, 1, 2, 3, 4].map((i) => (
                <li key={i} className="border-b border-slate-100 px-4 py-3 last:border-b-0">
                  <div className="h-3 w-16 rounded bg-slate-100" />
                  <div className="mt-2 h-3 w-40 rounded bg-slate-100" />
                </li>
              ))}
            {courses?.map((course) => (
              <li key={course.code} className="border-b border-slate-100 last:border-b-0">
                <button
                  type="button"
                  onClick={() => selectCourse(course.code)}
                  aria-current={course.code === selectedCode ? "true" : undefined}
                  className={`w-full px-4 py-3 text-left hover:bg-slate-50 ${
                    course.code === selectedCode ? "bg-red-50" : ""
                  }`}
                >
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="font-medium">
                      {completed.has(course.code) && (
                        <span className="mr-1 text-emerald-600" aria-label="Completed">
                          ✓
                        </span>
                      )}
                      {course.code}
                    </span>
                    <span className="shrink-0 text-xs text-slate-500">{formatCredits(course)}</span>
                  </span>
                  <span className="block text-sm text-slate-600">{course.name}</span>
                </button>
              </li>
            ))}
            {courses?.length === 0 && (
              <li className="px-4 py-8 text-center text-sm text-slate-500">
                No courses match &ldquo;{search}&rdquo;.
              </li>
            )}
          </ul>
        )}
      </section>

      <section
        ref={detailRef}
        aria-live="polite"
        className="scroll-mt-4 rounded-xl border border-slate-200 bg-surface p-6"
      >
        {detailError ? (
          <ErrorState message={detailError} onRetry={() => selectedCode && selectCourse(selectedCode)} />
        ) : selected ? (
          <CourseDetail selected={selected} completed={completed} onSelectCourse={selectCourse} />
        ) : selectedCode ? (
          <div role="status" className="space-y-3">
            <div className="h-4 w-20 rounded bg-slate-100" />
            <div className="h-6 w-64 rounded bg-slate-100" />
            <div className="h-3 w-full rounded bg-slate-100" />
          </div>
        ) : (
          <div className="py-10 text-center">
            <p className="font-medium text-slate-700">Select a course</p>
            <p className="mt-1 text-sm text-slate-500">
              See its credits, prerequisites, the full prerequisite chain, and what it unlocks.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
