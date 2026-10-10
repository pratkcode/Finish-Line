"use client";

import Link from "next/link";
import CourseEligibilityItem from "@/components/CourseEligibilityItem";
import StatusIcon from "@/components/StatusIcon";
import UnverifiedMajorNote from "@/components/UnverifiedMajorNote";
import ProgressBar from "@/components/ui/ProgressBar";
import { ErrorState, LoadingState, NoPlanState } from "@/components/ui/States";
import {
  getDegreeProgress,
  getEligibility,
  type CourseEligibility,
  type DegreeProgress,
  type EligibilityAnalysis,
  type Requirement,
  type RequirementSummary,
} from "@/lib/api";
import { useSessionData } from "@/lib/useSessionData";

const MAX_SUGGESTIONS = 6;

// Remaining courses by code, with their prerequisite status.
type EligibilityMap = Map<string, CourseEligibility>;

async function loadProgress(id: string) {
  // Eligibility only decorates the page, so a failure there isn't fatal.
  const [data, eligibility] = await Promise.all([
    getDegreeProgress(id),
    getEligibility(id).catch((): EligibilityAnalysis | null => null),
  ]);
  return { data, eligibility };
}

export default function DegreeProgressDashboard() {
  const { state, retry } = useSessionData(loadProgress);

  if (state.status === "loading") return <LoadingState label="Loading your progress" />;
  if (state.status === "no-plan") return <NoPlanState />;
  if (state.status === "error") return <ErrorState message={state.message} onRetry={retry} />;

  const { data, eligibility } = state.data;
  const byCode: EligibilityMap = new Map(
    [...(eligibility?.available ?? []), ...(eligibility?.blocked ?? [])].map((c) => [c.code, c]),
  );
  const units = orderedUnits(data);
  const sections = groupBy(units, (u) => u.path[0] ?? u.name);
  const done = data.completed_requirements.length;
  const tracked = done + data.remaining_requirements.length;

  return (
    <div className="space-y-6">
      <p className="text-lg font-semibold">
        {data.program.name}{" "}
        <span className="font-normal text-slate-500">· {data.program.university}</span>
      </p>

      {data.program.requirements_status !== "verified" && <UnverifiedMajorNote program={data.program} />}

      <OverallProgress data={data} done={done} tracked={tracked} />

      {eligibility && <EligibilitySummary eligibility={eligibility} />}

      {[...sections.entries()].map(([name, sectionUnits]) => (
        <Section key={name} name={name} units={sectionUnits} byCode={byCode} />
      ))}

      <p className="text-sm text-slate-500">
        Update your courses in{" "}
        <Link href="/profile" className="underline hover:text-slate-700">
          Profile
        </Link>
        , or see every rule in{" "}
        <Link href="/requirements" className="underline hover:text-slate-700">
          Requirements
        </Link>
        .
      </p>
    </div>
  );
}

function OverallProgress({
  data,
  done,
  tracked,
}: {
  data: DegreeProgress;
  done: number;
  tracked: number;
}) {
  const { from_courses, unverified, counted, required, remaining } = data.credits;
  const total = required ?? counted;
  return (
    <section className="grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-2">
      <div className="bg-white p-5">
        <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">Credits</p>
        <p className="mt-1.5 text-3xl font-bold tracking-tight">
          {counted} <span className="text-xl font-medium text-slate-400">/ {total}</span>
        </p>
        <div className="mt-3">
          <ProgressBar
            label="Credits toward degree"
            max={total}
            segments={[
              { value: from_courses, className: "bg-red-700", label: "From completed courses" },
              { value: unverified, className: "bg-red-300", label: "Reported, not matched to courses" },
            ]}
          />
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
          <li className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-red-700" />
            {from_courses} from courses
          </li>
          {unverified > 0 && (
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-300" />
              {unverified} reported, not matched
            </li>
          )}
          {remaining !== null && <li>{remaining} remaining</li>}
        </ul>
      </div>
      <div className="bg-white p-5">
        <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">Requirements</p>
        <p className="mt-1.5 text-3xl font-bold tracking-tight">
          {tracked ? Math.round((100 * done) / tracked) : 100}%{" "}
          <span className="text-xl font-medium text-slate-400">complete</span>
        </p>
        <div className="mt-3">
          <ProgressBar
            label="Requirements complete"
            max={tracked}
            segments={[{ value: done, className: "bg-emerald-600", label: "Complete" }]}
          />
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {done} of {tracked} requirements complete
        </p>
      </div>
    </section>
  );
}

function EligibilitySummary({ eligibility }: { eligibility: EligibilityAnalysis }) {
  const top = eligibility.missing_prerequisites.slice(0, 5);
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
        Remaining courses
      </h2>
      <p className="mt-2 text-sm text-slate-700">
        <span className="font-semibold text-emerald-700">{eligibility.available.length}</span>{" "}
        available now ·{" "}
        <span className="font-semibold text-red-700">{eligibility.blocked.length}</span> blocked
        by prerequisites
      </p>
      {top.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="text-slate-500">Prerequisites that unlock the most courses:</p>
          <ul className="mt-1 space-y-0.5">
            {top.map((m) => (
              <li key={m.code}>
                <span className="font-medium">{m.code}</span>{" "}
                <span className="text-slate-500">
                  unlocks {m.unlocks.length} {m.unlocks.length === 1 ? "course" : "courses"}
                  {m.status === "blocked" && " (needs its own prerequisites first)"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-400">
        Click a course below to see its prerequisites.
      </p>
    </section>
  );
}

function Section({
  name,
  units,
  byCode,
}: {
  name: string;
  units: RequirementSummary[];
  byCode: EligibilityMap;
}) {
  const tracked = units.filter((u) => u.status !== "not_tracked");
  const allDone = tracked.length > 0 && tracked.every((u) => u.status === "complete");
  const untracked = units.length - tracked.length;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{name}</h2>
        <span className="text-sm text-slate-500">
          {tracked.filter((u) => u.status === "complete").length} of {tracked.length} complete
        </span>
      </div>
      <div className="mt-3">
        <ProgressBar
          label={`${name} requirements complete`}
          max={tracked.length}
          size="sm"
          segments={[
            {
              value: tracked.filter((u) => u.status === "complete").length,
              className: "bg-emerald-600",
              label: "Complete",
            },
          ]}
        />
      </div>

      {allDone ? (
        <p className="mt-3 flex items-center gap-2 font-medium text-emerald-700">
          <StatusIcon status="complete" /> Completed
          {untracked > 0 && (
            <span className="font-normal text-slate-500">
              ({untracked} not tracked yet)
            </span>
          )}
        </p>
      ) : (
        <ul className="mt-4 space-y-4">
          {units.map((unit) => (
            <UnitRow key={unit.key} unit={unit} byCode={byCode} />
          ))}
        </ul>
      )}
    </section>
  );
}

function UnitRow({ unit, byCode }: { unit: RequirementSummary; byCode: EligibilityMap }) {
  const subPath = unit.path.slice(1).join(" › ");
  const remaining = remainingText(unit);
  const suggestions = unit.candidate_courses;

  return (
    <li className="flex items-start gap-3">
      <StatusIcon status={unit.status} />
      <div className="min-w-0 flex-1">
        {subPath && <p className="text-xs text-slate-400">{subPath}</p>}
        <p className={unit.status === "complete" ? "text-slate-700" : "font-medium"}>
          {unit.name}
          {remaining && <span className="font-normal text-slate-500"> · {remaining}</span>}
          {unit.status === "not_tracked" && (
            <span className="font-normal text-slate-400"> · Not tracked yet</span>
          )}
        </p>

        {unit.status !== "complete" && unit.options.length > 0 && (
          <p className="mt-0.5 text-sm text-slate-500">
            Complete one of: {unit.options.join("; ")}
          </p>
        )}

        {unit.status !== "complete" && unit.status !== "not_tracked" && (
          <Suggestions unit={unit} suggestions={suggestions} byCode={byCode} />
        )}
      </div>
    </li>
  );
}

function Suggestions({
  unit,
  suggestions,
  byCode,
}: {
  unit: RequirementSummary;
  suggestions: RequirementSummary["candidate_courses"];
  byCode: EligibilityMap;
}) {
  if (suggestions.length === 0) {
    // Credit totals where any course counts have no list to show.
    return unit.rule === "min_credits" ? null : (
      <p className="mt-1 text-sm text-slate-400">
        No matching courses in Finish Line&apos;s catalog yet. Check Testudo for options.
      </p>
    );
  }

  // Available courses first, then blocked; keep catalog order within each.
  const rank = (code: string) => (byCode.get(code)?.status === "blocked" ? 1 : 0);
  const sorted = [...suggestions].sort((a, b) => rank(a.code) - rank(b.code));
  const shown = sorted.slice(0, MAX_SUGGESTIONS);
  const hidden = sorted.slice(MAX_SUGGESTIONS);

  const item = (c: (typeof suggestions)[number]) => {
    const eligibility = byCode.get(c.code);
    return eligibility ? (
      <CourseEligibilityItem key={c.code} course={eligibility} />
    ) : (
      <li key={c.code} className="px-3 py-1 text-sm text-slate-600">
        {c.code} {c.name}
      </li>
    );
  };

  return (
    <div className="mt-2">
      <ul className="space-y-1.5">{shown.map(item)}</ul>
      {unit.candidate_count > suggestions.length && (
        <p className="mt-1.5 text-xs text-slate-500">
          Showing {suggestions.length} of {unit.candidate_count} courses that count, with verified
          prerequisites first. Search <Link href="/courses" className="underline">Courses</Link> for
          the rest.
        </p>
      )}
      {hidden.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-sm text-slate-500 underline hover:text-slate-700">
            {hidden.length} more {hidden.length === 1 ? "course" : "courses"}
          </summary>
          <ul className="mt-1.5 space-y-1.5">{hidden.map(item)}</ul>
        </details>
      )}
    </div>
  );
}

function remainingText(unit: RequirementSummary): string | null {
  if (unit.status === "complete" || unit.status === "not_tracked") return null;
  if (unit.credits_remaining) {
    return `${unit.credits_remaining} ${unit.credits_remaining === 1 ? "credit" : "credits"} remaining`;
  }
  if (unit.courses_remaining) {
    return `${unit.courses_remaining} ${unit.courses_remaining === 1 ? "course" : "courses"} remaining`;
  }
  return null;
}

// The API returns completed / remaining / untracked lists; show them in the
// order the requirements appear in the degree.
function orderedUnits(data: DegreeProgress): RequirementSummary[] {
  const order = new Map<string, number>();
  const visit = (nodes: Requirement[]) =>
    nodes.forEach((node) => {
      order.set(node.key, order.size);
      visit(node.children);
    });
  visit(data.requirements);
  return [
    ...data.completed_requirements,
    ...data.remaining_requirements,
    ...data.untracked_requirements,
  ].sort((a, b) => (order.get(a.key) ?? 0) - (order.get(b.key) ?? 0));
}

function groupBy<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    groups.set(k, [...(groups.get(k) ?? []), item]);
  }
  return groups;
}
