"use client";

import { useState } from "react";
import type { PlannedCourse, PlannedTerm } from "@/lib/api";
import { formatCredits } from "@/lib/api";
import { useCourseSearch } from "@/lib/useCourseSearch";

export type PlanActions = {
  add: (code: string, term: string) => void;
  move: (code: string, term: string) => void;
  remove: (code: string) => void;
  setCredits: (code: string, credits: number) => void;
};

type Props = {
  term: PlannedTerm; // may have no courses yet
  isLast: boolean;
  maxCredits: number;
  termChoices: string[];
  termOf: Map<string, string>; // planned course -> its semester
  completed: Set<string>;
  busy: boolean;
  actions: PlanActions;
};

export default function TermCard(props: Props) {
  const { term, isLast, maxCredits } = props;
  const [open, setOpen] = useState(true);
  const over = term.credits > maxCredits;
  const problems = term.warnings.length + term.courses.reduce((n, c) => n + c.warnings.length, 0);
  const bodyId = `term-${term.term.replace(" ", "-")}`;

  return (
    <li className="relative" data-term={term.term}>
      <span
        aria-hidden
        className={`absolute top-5 -left-[1.6rem] h-3 w-3 rounded-full border-2 border-white sm:-left-[1.85rem] ${
          isLast && term.courses.length ? "bg-red-700" : "bg-slate-400"
        }`}
      />
      <div className={`rounded-xl border bg-white ${problems ? "border-red-300" : "border-slate-200"}`}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex w-full items-center gap-4 px-5 py-4 text-left"
        >
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-lg font-semibold">{term.term}</span>
              {problems > 0 && (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">
                  ⚠ {problems} {problems === 1 ? "problem" : "problems"}
                </span>
              )}
            </span>
            <span className="mt-2 block h-2 w-full max-w-xs overflow-hidden rounded-full bg-slate-100">
              <span
                className={`block h-full ${over ? "bg-red-500" : "bg-slate-800"}`}
                style={{ width: `${Math.min((term.credits / maxCredits) * 100, 100)}%` }}
              />
            </span>
          </span>
          <span
            data-testid="term-credits"
            className={`shrink-0 text-sm font-medium ${over ? "text-red-700" : "text-slate-600"}`}
          >
            {term.credits} / {maxCredits} cr
          </span>
          <span aria-hidden className="shrink-0 text-slate-400">
            {open ? "▾" : "▸"}
          </span>
        </button>

        {open && (
          <div id={bodyId} className="border-t border-slate-100 px-5 pt-3 pb-4">
            {term.warnings.map((w) => (
              <p key={w} className="mb-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
                ⚠ {w}
              </p>
            ))}
            {term.courses.length === 0 ? (
              <p className="py-2 text-sm text-slate-500">No courses planned this semester.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {term.courses.map((c) => (
                  <CourseRow key={c.code} course={c} {...props} />
                ))}
              </ul>
            )}
            <AddCourse {...props} />
          </div>
        )}
      </div>
    </li>
  );
}

function CourseRow({ course, term, termChoices, termOf, busy, actions }: Props & { course: PlannedCourse }) {
  const variable = course.credits_min !== course.credits_max;
  return (
    <li className="py-3" data-course={course.code}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            <span className="font-semibold">{course.code} </span>
            <span className="text-slate-700">{course.name}</span>
            {!variable && <span className="text-slate-400"> · {course.credits} cr</span>}
            {course.retake && <span className="ml-2 text-xs text-amber-700">Retake (no new credits)</span>}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
            {course.satisfies.map((s) => (
              <span
                key={`${s.key}-${s.name}`}
                className={`rounded px-1.5 py-0.5 ${s.key ? "bg-sky-50 text-sky-800" : "bg-slate-100 text-slate-600"}`}
              >
                {s.key ? `Fills: ${s.name}` : s.name}
              </span>
            ))}
            {course.prerequisites.map((p) => (
              <span key={p} className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">
                After {p}
                {termOf.get(p) && <span className="text-slate-500"> ({termOf.get(p)})</span>}
              </span>
            ))}
          </div>
          {course.warnings.map((w) => (
            <p key={w} className="mt-1.5 text-xs font-medium text-red-700">
              ⚠ {w}
            </p>
          ))}
          {course.notes.map((n) => (
            <p key={n} className="mt-1 text-xs text-amber-800">
              {n}
            </p>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-2 text-xs">
          {variable && (
            <select
              aria-label={`Credits for ${course.code}`}
              value={course.credits}
              disabled={busy}
              onChange={(e) => actions.setCredits(course.code, Number(e.target.value))}
              className="rounded-md border border-slate-300 bg-white px-1.5 py-1 disabled:opacity-50"
            >
              {Array.from({ length: course.credits_max - course.credits_min + 1 }, (_, i) => course.credits_min + i).map(
                (n) => (
                  <option key={n} value={n}>
                    {n} cr
                  </option>
                ),
              )}
            </select>
          )}
          <select
            aria-label={`Move ${course.code} to another semester`}
            value=""
            disabled={busy}
            onChange={(e) => e.target.value && actions.move(course.code, e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-1.5 py-1 text-slate-700 disabled:opacity-50"
          >
            <option value="">Move to…</option>
            {termChoices
              .filter((t) => t !== term.term)
              .map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
          </select>
          <button
            type="button"
            disabled={busy}
            onClick={() => actions.remove(course.code)}
            className="text-slate-500 hover:text-red-700 disabled:opacity-50"
            aria-label={`Remove ${course.code} from the plan`}
          >
            Remove
          </button>
        </div>
      </div>
    </li>
  );
}

function AddCourse({ term, termOf, completed, busy, actions }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { results: found, error } = useCourseSearch(search, { limit: 6 });
  const results = found ?? [];

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 text-sm font-medium text-red-700 hover:underline"
      >
        + Add a course to {term.term}
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-lg border border-slate-200 p-3">
      <div className="flex items-center gap-2">
        <input
          type="search"
          autoFocus
          aria-label={`Search courses to add to ${term.term}`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by code or name"
          className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-red-700 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setSearch("");
          }}
          className="text-sm text-slate-500 hover:text-slate-800"
        >
          Cancel
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {results.length > 0 && (
        <ul data-testid="search-results" className="mt-2 divide-y divide-slate-100 text-sm">
          {results.map((c) => {
            const planned = termOf.get(c.code);
            return (
              <li key={c.code} className="flex items-center gap-3 py-1.5">
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{c.code}</span> <span className="text-slate-600">{c.name}</span>{" "}
                  <span className="text-slate-400">· {formatCredits(c)}</span>
                </span>
                {planned ? (
                  <span className="shrink-0 text-xs text-slate-400">In plan ({planned})</span>
                ) : completed.has(c.code) ? (
                  <span className="shrink-0 text-xs text-slate-400">Completed</span>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      actions.add(c.code, term.term);
                      setOpen(false);
                      setSearch("");
                    }}
                    className="shrink-0 rounded-md bg-red-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-50"
                  >
                    Add
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Finish Line checks prerequisites, credit limits, and which requirements the course fills once it&apos;s
        added.
      </p>
    </div>
  );
}
