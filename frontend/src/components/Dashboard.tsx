"use client";

import Link from "next/link";
import ProgressBar from "@/components/ui/ProgressBar";
import { ErrorState, LoadingState, NoPlanState } from "@/components/ui/States";
import { getDashboard, type DashboardSummary } from "@/lib/api";
import { useSessionData } from "@/lib/useSessionData";

export default function Dashboard() {
  const { state, retry } = useSessionData(getDashboard);

  if (state.status === "loading") return <LoadingState label="Loading your dashboard" rows={1} />;
  if (state.status === "no-plan") return <NoPlanState />;
  if (state.status === "error") return <ErrorState message={state.message} onRetry={retry} />;

  const d = state.data;
  return (
    <div className="space-y-6">
      <StudentCard d={d} />

      <section aria-label="Summary" className="grid gap-4 sm:grid-cols-3">
        <CreditsStat d={d} />
        <Stat label="Projected graduation" value={d.graduation.projected ?? "Not yet"}>
          {d.graduation.projected
            ? `${d.graduation.semesters} ${d.graduation.semesters === 1 ? "semester" : "semesters"} from ${d.current_term ?? "now"}`
            : "Some requirements can't be planned yet"}
          {d.graduation.warnings > 0 && (
            <span className="mt-1 block text-red-700">
              ⚠ {d.graduation.warnings} {d.graduation.warnings === 1 ? "problem" : "problems"} in your
              plan
            </span>
          )}
        </Stat>
        <Stat label="Requirements" value={`${d.requirements.percent}% complete`}>
          <ProgressBar
            label="Requirements complete"
            max={d.requirements.complete + d.requirements.remaining}
            segments={[{ value: d.requirements.complete, className: "bg-emerald-600", label: "Complete" }]}
            size="sm"
          />
          <span className="mt-2 block">
            {d.requirements.complete} of {d.requirements.complete + d.requirements.remaining} complete
          </span>
        </Stat>
      </section>

      {d.next_term && (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold text-slate-900">Up next: {d.next_term.term}</h2>
            <span className="text-sm text-slate-500">
              {d.next_term.credits} of {d.max_credits_per_term} credits
            </span>
          </div>
          <ul className="mt-3 flex flex-wrap gap-2">
            {d.next_term.courses.map((c) => (
              <li
                key={c}
                className={`rounded-md px-2.5 py-1 text-sm ${
                  /^[A-Z]{4}\d{3}/.test(c)
                    ? "bg-slate-100 font-medium text-slate-800"
                    : "border border-dashed border-slate-300 text-slate-500 italic"
                }`}
              >
                {c}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            From your generated plan, a recommendation and not an official UMD schedule.
          </p>
        </section>
      )}

      <section aria-label="Tools" className="grid gap-4 sm:grid-cols-2">
        <ToolCard href="/progress" title="Degree Progress">
          {d.requirements.remaining} requirements left · {d.credits.remaining ?? 0} credits to go
        </ToolCard>
        <ToolCard href="/graduation-plan" title="Graduation Plan">
          {d.graduation.projected
            ? `Graduate ${d.graduation.projected} · try what-ifs`
            : "See what's blocking a graduation date"}
        </ToolCard>
        <ToolCard
          href={d.top_prerequisite ? `/courses?code=${d.top_prerequisite.code}` : "/courses"}
          title="Course Dependencies"
        >
          {d.eligibility.available} courses available now · {d.eligibility.blocked} blocked
          {d.top_prerequisite && <> · {d.top_prerequisite.code} unlocks the most</>}
        </ToolCard>
        <ToolCard href="/courses" title="Course Search">
          Search the catalog by code or name
        </ToolCard>
      </section>
    </div>
  );
}

function StudentCard({ d }: { d: DashboardSummary }) {
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
      <dl className="grid flex-1 gap-x-8 gap-y-3 sm:grid-cols-3">
        <Field label="Major">{d.program.name}</Field>
        <Field label="University">{d.program.university}</Field>
        <Field label="Current semester">{d.current_term ?? "Not set"}</Field>
      </dl>
      <Link
        href="/profile"
        className="self-start rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:self-auto"
      >
        Edit profile
      </Link>
    </section>
  );
}

function CreditsStat({ d }: { d: DashboardSummary }) {
  const { earned, from_courses, unverified, required } = d.credits;
  return (
    <Stat label="Credits" value={`${earned} / ${required ?? "?"}`}>
      <ProgressBar
        label="Credits toward degree"
        max={required ?? earned}
        segments={[
          { value: from_courses, className: "bg-red-700", label: "From completed courses" },
          { value: unverified, className: "bg-red-300", label: "Reported, not matched to courses" },
        ]}
        size="sm"
      />
      <span className="mt-2 block">
        {from_courses} from {d.completed_courses} courses
        {unverified > 0 && ` · ${unverified} reported`}
      </span>
    </Stat>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{label}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{children}</dd>
    </div>
  );
}

function Stat({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{label}</p>
      <p className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
      <div className="mt-3 text-sm text-slate-500">{children}</div>
    </div>
  );
}

function ToolCard({ href, title, children }: { href: string; title: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="group rounded-xl border border-slate-200 bg-white p-5 hover:border-slate-300 hover:bg-slate-50"
    >
      <p className="flex items-center justify-between font-semibold text-slate-900">
        {title}
        <span aria-hidden className="text-slate-400 group-hover:text-slate-700">
          →
        </span>
      </p>
      <p className="mt-1 text-sm text-slate-600">{children}</p>
    </Link>
  );
}
