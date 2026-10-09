"use client";

import { useState } from "react";
import {
  addCompletedCourse,
  formatCredits,
  GRADES,
  removeCompletedCourse,
  updateCompletedCourse,
  type PlanSession,
} from "@/lib/api";
import { useCourseSearch } from "@/lib/useCourseSearch";


type Props = {
  session: PlanSession;
  onChange: (session: PlanSession) => void;
  onError: (message: string | null) => void;
};

export default function CompletedCourses({ session, onChange, onError }: Props) {
  const [search, setSearch] = useState("");
  const { results: found, error: searchError } = useCourseSearch(search, { limit: 8 });
  const results = found ?? [];
  const completed = new Set(session.courses.map((c) => c.code));

  async function run(action: () => Promise<PlanSession>) {
    try {
      onChange(await action());
      onError(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-semibold">Completed courses</h2>

      <label htmlFor="completed-search" className="mt-4 block text-sm font-medium text-slate-700">
        Search by code or name
      </label>
      <input
        id="completed-search"
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="e.g. INST326"
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-red-700 focus:outline-none focus:ring-1 focus:ring-red-700"
      />

      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {results.map((course) => (
            <li key={course.code} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="min-w-0 flex-1">
                <span className="font-medium">{course.code}</span>{" "}
                <span className="text-slate-600">{course.name}</span>{" "}
                <span className="text-slate-400">· {formatCredits(course)}</span>
              </span>
              {completed.has(course.code) ? (
                <span className="shrink-0 text-emerald-700">✓ Added</span>
              ) : (
                <button
                  type="button"
                  onClick={() => run(() => addCompletedCourse(session.id, course.code))}
                  className="shrink-0 rounded-md bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-800"
                >
                  Add completed course
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {searchError && <p className="mt-2 text-sm text-red-700">{searchError}</p>}
      {search.trim() && found !== null && results.length === 0 && !searchError && (
        <p className="mt-2 text-sm text-slate-500">No matching courses.</p>
      )}

      <ul className="mt-6 space-y-2">
        {session.courses.length === 0 && (
          <li className="text-sm text-slate-500">No completed courses yet.</li>
        )}
        {session.courses.map((course) => (
          <li
            key={course.code}
            className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-slate-50 px-4 py-2 text-sm"
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white">
              ✓
            </span>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{course.code}</span> – {course.name} –{" "}
              {course.credits} {course.credits === 1 ? "credit" : "credits"}
            </span>

            {course.credits_min !== course.credits_max && (
              <select
                aria-label={`Credits for ${course.code}`}
                value={course.credits}
                onChange={(e) =>
                  run(() =>
                    updateCompletedCourse(session.id, course.code, {
                      credits: Number(e.target.value),
                    }),
                  )
                }
                className="rounded border border-slate-300 bg-white px-2 py-1"
              >
                {range(course.credits_min, course.credits_max).map((n) => (
                  <option key={n} value={n}>
                    {n} cr
                  </option>
                ))}
              </select>
            )}

            <select
              aria-label={`Grade for ${course.code}`}
              value={course.grade ?? ""}
              onChange={(e) =>
                run(() =>
                  updateCompletedCourse(session.id, course.code, {
                    grade: e.target.value || null,
                  }),
                )
              }
              className="rounded border border-slate-300 bg-white px-2 py-1"
            >
              <option value="">Grade</option>
              {GRADES.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => run(() => removeCompletedCourse(session.id, course.code))}
              className="text-slate-500 hover:text-red-700"
              aria-label={`Remove ${course.code}`}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function range(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}
