"use client";

import { useEffect, useState } from "react";
import CompletedCourses from "@/components/CompletedCourses";
import UnverifiedMajorNote from "@/components/UnverifiedMajorNote";
import { ErrorState, LoadingState } from "@/components/ui/States";
import {
  ApiError,
  createSession,
  deleteSession,
  getPrograms,
  getSession,
  updateSession,
  type PlanSession,
  type Program,
  type SessionChanges,
} from "@/lib/api";
import { readSessionId, writeSessionId } from "@/lib/session";

// Rough mapping of today's date to a UMD term, used as the default.
function currentTerm(date = new Date()): string {
  const month = date.getMonth() + 1;
  const season = month === 1 ? "Winter" : month <= 5 ? "Spring" : month <= 8 ? "Summer" : "Fall";
  return `${season} ${date.getFullYear()}`;
}

function termOptions(): string[] {
  const year = new Date().getFullYear();
  const terms = [];
  for (let y = year - 2; y <= year + 4; y++) {
    for (const season of ["Winter", "Spring", "Summer", "Fall"]) {
      terms.push(`${season} ${y}`);
    }
  }
  return terms;
}

// Shared so that running the load twice (React does in development) creates
// at most one session.
let pendingSession: Promise<PlanSession> | null = null;

function loadOrCreateSession(programs: Program[]): Promise<PlanSession> {
  pendingSession ??= fetchOrCreateSession(programs).finally(() => {
    pendingSession = null;
  });
  return pendingSession;
}

async function fetchOrCreateSession(programs: Program[]): Promise<PlanSession> {
  const savedId = readSessionId();
  if (savedId) {
    try {
      return await getSession(savedId);
    } catch (err) {
      // The saved session is gone (e.g. the database was reset): start fresh.
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 422))) throw err;
    }
  }
  const session = await createSession({
    program_slug: programs[0].slug,
    current_term: currentTerm(),
    max_credits_per_term: 15,
  });
  writeSessionId(session.id);
  return session;
}

export default function ProfileEditor() {
  const [programs, setPrograms] = useState<Program[]>([]);
  const [session, setSession] = useState<PlanSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    getPrograms()
      .then(async (list) => {
        setPrograms(list);
        setSession(await loadOrCreateSession(list));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load your profile."));
  }, [attempt]);

  async function save(changes: SessionChanges) {
    if (!session) return;
    try {
      setSession(await updateSession(session.id, changes));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your changes.");
    }
  }

  async function startOver() {
    if (!session || !confirm("Clear your profile and completed courses?")) return;
    try {
      await deleteSession(session.id);
    } catch {
      // Already gone; create a new one anyway.
    }
    writeSessionId(null);
    try {
      setSession(await loadOrCreateSession(programs));
      setError(null);
    } catch (err) {
      setSession(null);
      setError(err instanceof Error ? err.message : "Couldn't start a new profile.");
    }
  }

  if (!session) {
    return error ? (
      <ErrorState
        message={error}
        onRetry={() => {
          setError(null);
          setAttempt((n) => n + 1);
        }}
      />
    ) : (
      <LoadingState label="Loading your profile" rows={2} />
    );
  }

  const universities = [...new Set(programs.map((p) => p.university))];
  const majors = programs.filter((p) => p.university === session.university);
  const currentProgram = programs.find((p) => p.slug === session.program_slug);

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Profile</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="University">
            <select
              value={session.university}
              onChange={(e) => {
                const first = programs.find((p) => p.university === e.target.value);
                if (first) save({ program_slug: first.slug });
              }}
              className={inputClass}
            >
              {universities.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </Field>

          <Field
            label="Major"
            hint="Changing your major keeps your completed courses and plan, and rechecks them against the new major."
          >
            <select
              id="major"
              value={session.program_slug}
              onChange={(e) => save({ program_slug: e.target.value })}
              className={inputClass}
            >
              <optgroup label="Requirements verified">
                {majors
                  .filter((p) => p.requirements_status === "verified")
                  .map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name}
                    </option>
                  ))}
              </optgroup>
              <optgroup label="Requirements not verified yet">
                {majors
                  .filter((p) => p.requirements_status !== "verified")
                  .map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name} (not verified yet)
                    </option>
                  ))}
              </optgroup>
            </select>
          </Field>

          <Field label="Current semester">
            <select
              value={session.current_term ?? ""}
              onChange={(e) => save({ current_term: e.target.value || null })}
              className={inputClass}
            >
              <option value="">Not set</option>
              {termOptions().map((term) => (
                <option key={term}>{term}</option>
              ))}
            </select>
          </Field>

          <Field label="Maximum credits per semester">
            <NumberInput
              key={session.max_credits_per_term}
              value={session.max_credits_per_term}
              min={1}
              max={30}
              onSave={(value) => value !== null && save({ max_credits_per_term: value })}
            />
          </Field>

          <Field
            label="Total completed credits"
            hint="Include AP, transfer, and other credit. Your course list below is used to check it."
          >
            <NumberInput
              key={session.credits.reported ?? "none"}
              value={session.credits.reported}
              min={0}
              max={300}
              placeholder="e.g. 61"
              onSave={(value) => save({ reported_credits: value })}
            />
          </Field>
        </div>
      </section>

      {currentProgram && currentProgram.requirements_status !== "verified" && (
        <UnverifiedMajorNote program={currentProgram} />
      )}

      <CreditSummary session={session} />

      <CompletedCourses session={session} onChange={setSession} onError={setError} />

      <button
        type="button"
        onClick={startOver}
        className="text-sm text-slate-500 underline hover:text-slate-700"
      >
        Start over
      </button>
    </div>
  );
}

function CreditSummary({ session }: { session: PlanSession }) {
  const { completed, reported, unmatched, reported_too_low } = session.credits;
  const count = session.courses.length;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <p className="text-sm text-slate-500">Completed credits</p>
      <p className="mt-1 text-3xl font-bold">{completed}</p>
      <p className="text-sm text-slate-500">
        from {count} {count === 1 ? "course" : "courses"} in your list
      </p>
      {reported_too_low && (
        <p className="mt-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You entered {reported} total credits, but your courses add up to {completed}. Using{" "}
          {completed}.
        </p>
      )}
      {unmatched > 0 && (
        <p className="mt-3 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700">
          You entered {reported} total credits. {unmatched} of those aren&apos;t matched to a
          course yet (AP, transfer, or courses you haven&apos;t added). Add courses below so they
          can count toward specific requirements.
        </p>
      )}
    </section>
  );
}

function NumberInput({
  value,
  min,
  max,
  placeholder,
  onSave,
}: {
  value: number | null;
  min: number;
  max: number;
  placeholder?: string;
  onSave: (value: number | null) => void;
}) {
  // Callers pass key={value}, so a new saved value resets the draft.
  const [draft, setDraft] = useState(value === null ? "" : String(value));

  function commit() {
    const trimmed = draft.trim();
    const parsed = trimmed === "" ? null : Number(trimmed);
    if (parsed !== null && (!Number.isInteger(parsed) || parsed < min || parsed > max)) {
      setDraft(value === null ? "" : String(value));
      return;
    }
    if (parsed !== value) onSave(parsed);
  }

  return (
    <input
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      className={inputClass}
    />
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{message}</p>;
}

const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-red-700 focus:outline-none focus:ring-1 focus:ring-red-700";
