"use client";

import Link from "next/link";
import { useState } from "react";
import PlanSummary from "@/components/plan/PlanSummary";
import RecommendationPanel from "@/components/plan/RecommendationPanel";
import TermCard, { type PlanActions } from "@/components/plan/TermCard";
import { ErrorState, LoadingState, NoPlanState } from "@/components/ui/States";
import {
  acceptRecommendation,
  addPlannedCourse,
  clearPlan,
  getPlan,
  getRecommendation,
  getSession,
  removePlannedCourse,
  updatePlannedCourse,
  type PlannedTerm,
  type Recommendation,
  type StudentPlan,
} from "@/lib/api";
import { useSessionData } from "@/lib/useSessionData";

async function loadPlan(id: string) {
  const [plan, session] = await Promise.all([getPlan(id), getSession(id)]);
  return { plan, completed: new Set(session.courses.map((c) => c.code)) };
}

function nextTerm(term: string): string {
  const [season, year] = term.split(" ");
  return season === "Fall" ? `Spring ${Number(year) + 1}` : `Fall ${year}`;
}

function termOrder(term: string): number {
  const [season, year] = term.split(" ");
  return Number(year) * 2 + (season === "Fall" ? 1 : 0);
}

export default function GraduationPlanView() {
  const { state, setState, retry } = useSessionData(loadPlan);
  const [extraTerms, setExtraTerms] = useState<string[]>([]); // empty semesters the student added
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.status === "loading") return <LoadingState label="Loading your plan" />;
  if (state.status === "no-plan") return <NoPlanState />;
  if (state.status === "error") return <ErrorState message={state.message} onRetry={retry} />;

  const { sessionId } = state;
  const { plan, completed } = state.data;

  // Every change goes to the API, and the page shows the plan it returns, so
  // credits always match what's saved.
  async function run(change: () => Promise<StudentPlan>) {
    setBusy(true);
    try {
      const updated = await change();
      setState({ status: "ready", sessionId, data: { plan: updated, completed } });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update your plan.");
    } finally {
      setBusy(false);
    }
  }

  const actions: PlanActions = {
    add: (code, term) => run(() => addPlannedCourse(sessionId, code, term)),
    move: (code, term) => run(() => updatePlannedCourse(sessionId, code, { term })),
    remove: (code) => run(() => removePlannedCourse(sessionId, code)),
    setCredits: (code, credits) => run(() => updatePlannedCourse(sessionId, code, { credits })),
  };

  async function recommend() {
    setBusy(true);
    try {
      setRecommendation(await getRecommendation(sessionId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't build a recommendation.");
    } finally {
      setBusy(false);
    }
  }

  async function accept() {
    if (!recommendation) return;
    const courses = recommendation.additions.map((c) => ({ code: c.code as string, term: c.term }));
    await run(() => acceptRecommendation(sessionId, courses));
    setRecommendation(null);
  }

  // Every semester from the current one through one past the last planned (or
  // added) semester, so there's always somewhere to add a course.
  const furthest = [...plan.terms.map((t) => t.term), ...extraTerms, plan.current_term].sort(
    (a, b) => termOrder(a) - termOrder(b),
  ).at(-1)!;
  const terms: PlannedTerm[] = [];
  for (let t = plan.current_term; termOrder(t) <= termOrder(furthest) + 1; t = nextTerm(t)) {
    terms.push(plan.terms.find((p) => p.term === t) ?? { term: t, credits: 0, warnings: [], courses: [] });
  }
  const termChoices = [...terms.map((t) => t.term), nextTerm(terms.at(-1)!.term)];
  const termOf = new Map<string, string>();
  plan.terms.forEach((t) => t.courses.forEach((c) => termOf.set(c.code, t.term)));
  const lastPlanned = plan.terms.at(-1)?.term;

  return (
    <div className="space-y-6">
      {!plan.requirements_verified && (
        <section role="note" className="rounded-xl border border-slate-300 bg-white p-4 text-sm text-slate-700">
          <p className="font-semibold text-slate-900">
            Requirements for {plan.program_name} aren&apos;t verified in Finish Line yet
          </p>
          <p className="mt-1">
            You can still build a plan. Finish Line checks prerequisites, credit limits, and university and Gen Ed
            requirements, but it can&apos;t check major requirements or recommend a plan for this major.{" "}
            <Link href="/profile" className="underline">
              Change major
            </Link>
          </p>
        </section>
      )}

      <PlanSummary plan={plan} />

      <section className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={recommend}
          disabled={busy || !plan.requirements_verified}
          className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
        >
          {plan.terms.length ? "Recommend courses for the rest of my plan" : "Generate a recommended plan"}
        </button>
        {plan.terms.length > 0 && (
          <button
            type="button"
            disabled={busy}
            onClick={() => confirm("Remove every course from your plan?") && run(() => clearPlan(sessionId))}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Clear plan
          </button>
        )}
        <p className="text-xs text-slate-500">
          Optional. Recommendations are only added when you choose to, and you can edit them afterwards.
        </p>
      </section>

      {recommendation && (
        <RecommendationPanel
          recommendation={recommendation}
          busy={busy}
          onAccept={accept}
          onDismiss={() => setRecommendation(null)}
        />
      )}

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {plan.warnings.length > 0 && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-semibold">
            {plan.warnings.length} {plan.warnings.length === 1 ? "problem" : "problems"} with this plan
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {plan.warnings.map((w, i) => (
              <li key={i}>
                <span className="font-medium">
                  {w.term}
                  {w.code && ` · ${w.code}`}:
                </span>{" "}
                {w.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan.terms.length === 0 && !recommendation && (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-4 text-sm text-slate-600">
          Your plan is empty. Add courses to a semester below, or generate a recommended plan to start from.
        </p>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold tracking-wider text-slate-500 uppercase">Semesters</h2>
        <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5 sm:pl-6">
          {terms.map((t) => (
            <TermCard
              key={t.term}
              term={t}
              isLast={t.term === lastPlanned}
              maxCredits={plan.max_credits_per_term}
              termChoices={termChoices}
              termOf={termOf}
              completed={completed}
              busy={busy}
              actions={actions}
            />
          ))}
        </ol>
        <button
          type="button"
          onClick={() => setExtraTerms([...extraTerms, nextTerm(terms.at(-1)!.term)])}
          className="mt-3 ml-5 text-sm font-medium text-slate-600 hover:text-slate-900 sm:ml-6"
        >
          + Add a semester
        </button>
      </section>

      {plan.still_needed.length > 0 && plan.requirements_verified && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
          <p className="font-semibold text-slate-900">Still needed after this plan</p>
          <ul className="mt-2 grid gap-1 text-slate-700 sm:grid-cols-2">
            {plan.still_needed.map((u) => (
              <li key={u.key}>
                {u.name}
                <span className="text-slate-500">
                  {u.credits_remaining ? ` · ${u.credits_remaining} credits` : ""}
                  {u.courses_remaining ? ` · ${u.courses_remaining} ${u.courses_remaining === 1 ? "course" : "courses"}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            See which courses count in <Link href="/progress" className="underline">Degree Progress</Link>.
          </p>
        </section>
      )}

      <footer className="space-y-2 border-t border-slate-200 pt-6 text-sm text-slate-500">
        <p>
          Finish Line is a planning tool, not an official UMD schedule or degree audit. It doesn&apos;t know which
          semesters courses are offered. Confirm your plan with an advisor.
        </p>
        {plan.not_checked.length > 0 && <p>Not checked: {plan.not_checked.map((n) => n.name).join(", ")}.</p>}
        <p>
          <Link href="/profile" className="underline hover:text-slate-700">
            Edit completed courses, major, and credit limit
          </Link>
        </p>
      </footer>
    </div>
  );
}
