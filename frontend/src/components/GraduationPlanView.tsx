"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PlanSummary from "@/components/plan/PlanSummary";
import TermCard from "@/components/plan/TermCard";
import { ErrorState, LoadingState, NoPlanState } from "@/components/ui/States";
import WhatIfBar from "@/components/plan/WhatIfBar";
import {
  ApiError,
  getGraduationPlan,
  previewPlan,
  savePlanOverrides,
  type GraduationPlan,
  type PlanOverrides,
  type PlanPreview,
} from "@/lib/api";
import { readSessionId } from "@/lib/session";

type Load =
  | { kind: "loading" }
  | { kind: "no-plan" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

// The student's edits, as actions on the overrides sent to the API.
export type PlanActions = {
  move: (code: string, term: string) => void; // also used to add a course
  remove: (code: string) => void;
  restore: (code: string) => void; // undo a remove or a placement
};

function overridesOf(plan: GraduationPlan): PlanOverrides {
  return { pinned: plan.pinned, removed: plan.removed };
}

export default function GraduationPlanView() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [saved, setSaved] = useState<GraduationPlan | null>(null);
  // Unsaved what-if changes and their preview.
  const [draft, setDraft] = useState<PlanOverrides | null>(null);
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = readSessionId();
    if (!id) {
      queueMicrotask(() => setLoad({ kind: "no-plan" }));
      return;
    }
    getGraduationPlan(id)
      .then((plan) => {
        setSessionId(id);
        setSaved(plan);
        setLoad({ kind: "ready" });
      })
      .catch((err) =>
        setLoad(
          err instanceof ApiError && err.status === 404
            ? { kind: "no-plan" }
            : { kind: "error", message: err instanceof Error ? err.message : "Couldn't load your plan." },
        ),
      );
  }, []);

  async function change(edit: (o: PlanOverrides) => PlanOverrides) {
    if (!sessionId || !saved) return;
    const next = edit(draft ?? overridesOf(saved));
    setBusy(true);
    try {
      setPreview(await previewPlan(sessionId, next));
      setDraft(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update the plan.");
    } finally {
      setBusy(false);
    }
  }

  const actions: PlanActions = {
    move: (code, term) =>
      change((o) => ({
        pinned: [...o.pinned.filter((p) => p.code !== code), { code, term }],
        removed: o.removed.filter((c) => c !== code),
      })),
    remove: (code) =>
      change((o) => ({
        pinned: o.pinned.filter((p) => p.code !== code),
        removed: [...o.removed.filter((c) => c !== code), code],
      })),
    restore: (code) =>
      change((o) => ({
        pinned: o.pinned.filter((p) => p.code !== code),
        removed: o.removed.filter((c) => c !== code),
      })),
  };

  async function save() {
    if (!sessionId || !draft) return;
    setBusy(true);
    try {
      setSaved(await savePlanOverrides(sessionId, draft));
      setDraft(null);
      setPreview(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save the plan.");
    } finally {
      setBusy(false);
    }
  }

  function discard() {
    setDraft(null);
    setPreview(null);
    setError(null);
  }

  async function resetAll() {
    if (!sessionId) return;
    setBusy(true);
    try {
      setSaved(await savePlanOverrides(sessionId, { pinned: [], removed: [] }));
      discard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reset the plan.");
    } finally {
      setBusy(false);
    }
  }

  if (load.kind === "loading") return <LoadingState label="Building your plan" />;
  if (load.kind === "error") return <ErrorState message={load.message} onRetry={() => location.reload()} />;
  if (load.kind === "no-plan" || !saved) return <NoPlanState />;

  const plan: GraduationPlan = preview ?? saved;
  const changed = new Set(preview?.changes.moved.map((m) => m.code) ?? []);
  const termOf = new Map<string, string>();
  plan.terms.forEach((t) => t.courses.forEach((c) => c.code && termOf.set(c.code, t.term)));
  const termChoices = upcomingTerms(plan);
  const hasChanges = plan.pinned.length > 0 || plan.removed.length > 0;

  return (
    <div className="space-y-6">
      <PlanSummary plan={plan} before={preview?.changes.graduation_before} draft={Boolean(draft)} />

      {draft && preview && (
        <DraftBanner preview={preview} busy={busy} onSave={save} onDiscard={discard} />
      )}

      <WhatIfBar plan={plan} terms={termChoices} busy={busy} onTry={actions.move} />

      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

      {plan.warnings.length > 0 && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-semibold">
            {plan.warnings.length} {plan.warnings.length === 1 ? "problem" : "problems"} with
            this plan
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

      <Timeline
        plan={plan}
        termOf={termOf}
        termChoices={termChoices}
        changed={changed}
        busy={busy}
        actions={actions}
      />

      {plan.removed.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
          <p className="font-medium text-slate-700">Removed from your plan</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {plan.removed.map((code) => (
              <span
                key={code}
                className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1"
              >
                <span className="text-slate-500 line-through">{code}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => actions.restore(code)}
                  className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                >
                  Restore
                </button>
              </span>
            ))}
          </div>
        </section>
      )}

      <Problems plan={plan} />

      <footer className="space-y-3 border-t border-slate-200 pt-6 text-sm text-slate-500">
        <p>
          <span className="font-medium text-slate-700">Recommendation only.</span>{" "}
          {plan.disclaimer}
        </p>
        <details>
          <summary className="cursor-pointer hover:text-slate-700">How this plan was made</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {plan.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
            {plan.not_checked.length > 0 && (
              <li>Not checked: {plan.not_checked.map((n) => n.name).join(", ")}.</li>
            )}
          </ul>
        </details>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          <Link href="/profile" className="underline hover:text-slate-700">
            Edit courses and credit limit
          </Link>
          {hasChanges && !draft && (
            <button
              type="button"
              onClick={resetAll}
              disabled={busy}
              className="underline hover:text-slate-700 disabled:opacity-50"
            >
              Reset to the generated plan
            </button>
          )}
        </p>
      </footer>
    </div>
  );
}

function DraftBanner({
  preview,
  busy,
  onSave,
  onDiscard,
}: {
  preview: PlanPreview;
  busy: boolean;
  onSave: () => void;
  onDiscard: () => void;
}) {
  const { graduation_before: before, graduation_after: after, moved } = preview.changes;
  return (
    <section className="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-amber-950">
          <p className="font-semibold">What-if: unsaved changes</p>
          <p className="mt-0.5">
            Graduation {before ?? "—"} → <span className="font-semibold">{after ?? "can't be projected"}</span>
            {" · "}
            {moved.length} {moved.length === 1 ? "course" : "courses"} changed
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onDiscard}
            disabled={busy}
            className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100 disabled:opacity-50"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={busy}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Save changes
          </button>
        </div>
      </div>
      {moved.length > 0 && (
        <ul className="mt-3 grid gap-x-6 gap-y-0.5 text-xs text-amber-900 sm:grid-cols-2">
          {moved.map((m) => (
            <li key={m.code}>
              <span className="font-medium">{m.code}</span>: {m.from_term ?? "not planned"} →{" "}
              {m.to_term ?? "removed"}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Timeline({
  plan,
  termOf,
  termChoices,
  changed,
  busy,
  actions,
}: {
  plan: GraduationPlan;
  termOf: Map<string, string>;
  termChoices: string[];
  changed: Set<string>;
  busy: boolean;
  actions: PlanActions;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const allCollapsed = plan.terms.length > 0 && plan.terms.every((t) => collapsed.has(t.term));
  const planned = new Set(termOf.keys());

  function toggle(term: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Semesters</h2>
        {plan.terms.length > 1 && (
          <button
            type="button"
            onClick={() =>
              setCollapsed(allCollapsed ? new Set() : new Set(plan.terms.map((t) => t.term)))
            }
            className="text-sm text-slate-500 hover:text-slate-800"
          >
            {allCollapsed ? "Expand all" : "Collapse all"}
          </button>
        )}
      </div>
      <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5 sm:pl-6">
        {plan.terms.map((term, i) => (
          <TermCard
            key={term.term}
            term={term}
            isLast={i === plan.terms.length - 1}
            maxCredits={plan.max_credits_per_term}
            open={!collapsed.has(term.term)}
            onToggle={() => toggle(term.term)}
            termOf={termOf}
            termChoices={termChoices}
            planned={planned}
            changed={changed}
            busy={busy}
            actions={actions}
          />
        ))}
      </ol>
    </section>
  );
}

function Problems({ plan }: { plan: GraduationPlan }) {
  if (plan.unscheduled.length === 0 && plan.unplanned_requirements.length === 0) return null;
  return (
    <section className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">Couldn&apos;t be planned</p>
      <ul className="mt-1.5 space-y-0.5">
        {plan.unscheduled.map((c, i) => (
          <li key={c.code ?? `${c.name}-${i}`}>
            <span className="font-medium">{c.code ?? c.name}</span>: {c.reason}
          </li>
        ))}
        {plan.unplanned_requirements.map((r) => (
          <li key={r.key}>
            <span className="font-medium">{r.name}</span>: {r.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

// Terms the student can place courses in: the plan's terms plus two more.
function upcomingTerms(plan: GraduationPlan): string[] {
  const terms = plan.terms.map((t) => t.term);
  let last = terms.at(-1) ?? plan.start_term;
  if (terms.length === 0) terms.push(last);
  for (let i = 0; i < 2; i++) {
    const [season, year] = last.split(" ");
    last = season === "Fall" ? `Spring ${Number(year) + 1}` : `Fall ${year}`;
    terms.push(last);
  }
  return terms;
}
