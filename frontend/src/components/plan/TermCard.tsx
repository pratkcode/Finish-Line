"use client";

import { useState } from "react";
import type { PlanActions } from "@/components/GraduationPlanView";
import { formatCredits, type PlannedCourse, type PlannedTerm } from "@/lib/api";
import { useCourseSearch } from "@/lib/useCourseSearch";

type Props = {
  term: PlannedTerm;
  isLast: boolean;
  maxCredits: number;
  open: boolean;
  onToggle: () => void;
  termOf: Map<string, string>;
  termChoices: string[];
  planned: Set<string>; // codes already in the plan
  changed: Set<string>; // codes moved by the current what-if
  busy: boolean;
  actions: PlanActions;
};

export default function TermCard(props: Props) {
  const { term, isLast, maxCredits, open, onToggle } = props;
  const over = term.credits > maxCredits;
  const problems =
    term.warnings.length + term.courses.reduce((n, c) => n + c.warnings.length, 0);
  const bodyId = `term-${term.term.replace(" ", "-")}`;

  return (
    <li className="relative">
      {/* Timeline dot */}
      <span
        aria-hidden
        className={`absolute top-5 -left-[1.6rem] h-3 w-3 rounded-full border-2 border-white sm:-left-[1.85rem] ${
          isLast ? "bg-red-700" : "bg-slate-400"
        }`}
      />
      <div
        className={`rounded-xl border bg-white ${problems ? "border-red-300" : "border-slate-200"}`}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex w-full items-center gap-4 px-5 py-4 text-left"
        >
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-lg font-semibold">{term.term}</span>
              {isLast && (
                <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700">
                  Graduation semester
                </span>
              )}
              {problems > 0 && (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">
                  ⚠ {problems} {problems === 1 ? "problem" : "problems"}
                </span>
              )}
            </span>
            <span className="mt-2 flex items-center gap-3">
              <span className="h-2 w-full max-w-xs overflow-hidden rounded-full bg-slate-100">
                <span
                  className={`block h-full ${over ? "bg-red-500" : "bg-slate-800"}`}
                  style={{ width: `${Math.min((term.credits / maxCredits) * 100, 100)}%` }}
                />
              </span>
            </span>
          </span>
          <span className={`shrink-0 text-sm font-medium ${over ? "text-red-700" : "text-slate-600"}`}>
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
              <p className="py-2 text-sm text-slate-500">No courses this semester.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {term.courses.map((c, i) => (
                  <CourseRow key={c.code ?? `${c.name}-${i}`} course={c} {...props} />
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

function CourseRow({
  course,
  term,
  termOf,
  termChoices,
  changed,
  busy,
  actions,
}: Props & { course: PlannedCourse }) {
  const isSlot = course.code === null;
  const code = course.code;
  return (
    <li className={`py-3 ${code && changed.has(code) ? "-mx-2 rounded-md bg-amber-50 px-2" : ""}`}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            {code && <span className="font-semibold">{code} </span>}
            <span className={isSlot ? "text-slate-500 italic" : "text-slate-700"}>{course.name}</span>
            <span className="text-slate-400"> · {course.credits} cr</span>
            {course.pinned && (
              <span className="ml-2 rounded bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-white">
                Placed by you
              </span>
            )}
            {course.retake && <span className="ml-2 text-xs text-amber-700">Retake</span>}
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

        {code && (
          <div className="flex shrink-0 items-center gap-2 text-xs">
            <select
              aria-label={`Move ${code} to another semester`}
              value=""
              disabled={busy}
              onChange={(e) => e.target.value && actions.move(code, e.target.value)}
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
            {course.pinned && (
              <button
                type="button"
                disabled={busy}
                onClick={() => actions.restore(code)}
                className="text-slate-500 hover:text-slate-900 disabled:opacity-50"
                title="Let the planner choose the semester again"
              >
                Unpin
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => actions.remove(code)}
              className="text-slate-500 hover:text-red-700 disabled:opacity-50"
              aria-label={`Remove ${code} from the plan`}
            >
              Remove
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

function AddCourse({ term, planned, busy, actions }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { results: found, error: searchError } = useCourseSearch(search, { limit: 6 });
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
      {searchError && <p className="mt-2 text-sm text-red-700">{searchError}</p>}
      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {results.map((c) => (
            <li key={c.code} className="flex items-center gap-3 py-1.5">
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{c.code}</span>{" "}
                <span className="text-slate-600">{c.name}</span>{" "}
                <span className="text-slate-400">· {formatCredits(c)}</span>
              </span>
              {planned.has(c.code) ? (
                <span className="shrink-0 text-xs text-slate-400">In plan</span>
              ) : (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    actions.move(c.code, term.term);
                    setOpen(false);
                    setSearch("");
                  }}
                  className="shrink-0 rounded-md bg-red-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-50"
                >
                  Add
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Adding a course plans its prerequisites too. You&apos;ll see a warning if it can&apos;t be
        taken this semester.
      </p>
    </div>
  );
}
