"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorState, LoadingState, NoPlanState } from "@/components/ui/States";
import {
  addCompletedCourse,
  addFulfillment,
  addHistoryTerm,
  addTransfer,
  formatCredits,
  getHistory,
  GRADES,
  removeCompletedCourse,
  removeFulfillment,
  removeHistoryTerm,
  removeTransfer,
  updateCompletedCourse,
  updateFulfillment,
  updateHistoryTerm,
  updateTransfer,
  type AcademicHistory as History,
  type CourseStatus,
  type FulfillmentMethod,
  type FulfillmentVerification,
  type HistoryCourse,
  type HistoryTerm,
  type TransferCredit,
  type TransferInput,
  type TransferVerification,
} from "@/lib/api";
import { useCourseSearch } from "@/lib/useCourseSearch";
import { useSessionData } from "@/lib/useSessionData";



const METHODS: Record<FulfillmentMethod, string> = {
  transfer_credit: "Transfer credit evaluation",
  exam_credit: "AP/IB or other exam credit",
  waiver: "Waiver",
  substitution: "Approved substitution",
  associate_degree: "Associate degree",
  other: "Other",
};

const VERIFICATION: Record<FulfillmentVerification, string> = {
  student_reported: "Reported by me (not verified)",
  umd_verified: "Verified by UMD",
  approved_exception: "Approved exception",
};

type Actions = {
  run: (change: () => Promise<unknown>) => Promise<boolean>;
  sessionId: string;
  busy: boolean;
};

export default function AcademicHistory() {
  const { state, setState, retry } = useSessionData(getHistory);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.status === "loading") return <LoadingState label="Loading your academic history" />;
  if (state.status === "no-plan") return <NoPlanState />;
  if (state.status === "error") return <ErrorState message={state.message} onRetry={retry} />;

  const { sessionId, data: history } = state;

  // Every change is saved, then the page shows the history the API returns.
  async function run(change: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    try {
      await change();
      setState({ status: "ready", sessionId, data: await getHistory(sessionId) });
      setError(null);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save that change.");
      return false;
    } finally {
      setBusy(false);
    }
  }
  const actions: Actions = { run, sessionId, busy };

  return (
    <div className="space-y-6">
      <Summary history={history} />

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Semesters</h2>
        <p className="text-sm text-slate-500">
          Add each semester you attended, at UMD or another school, oldest first or in any order. Your current
          semester is {history.current_term} (change it in{" "}
          <Link href="/profile" className="underline">
            Profile
          </Link>
          ).
        </p>
        {history.terms.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-4 text-sm text-slate-600">
            No semesters yet. Starting at UMD as a first-year? Add your current semester and the courses you&apos;re
            taking. Transferring? Add your semesters at your previous schools.
          </p>
        )}
        <ol className="space-y-3">
          {history.terms.map((t) => (
            <TermSection key={t.id} term={t} actions={actions} />
          ))}
        </ol>
        <AddTermForm actions={actions} />
      </section>

      <Unassigned history={history} actions={actions} />

      <Fulfillments history={history} actions={actions} />

      <footer className="border-t border-slate-200 pt-6 text-sm text-slate-500">
        Finish Line isn&apos;t an official UMD degree audit. Only mark transfer credit or a requirement as verified when
        UMD has evaluated it (for example, it appears on your UMD transcript or degree audit). Reported items are
        shown but never counted.
      </footer>
    </div>
  );
}

function Summary({ history }: { history: History }) {
  const { earned_credits, applicable_credits, in_progress_credits, pending } = history.summary;
  return (
    <section
      aria-label="History summary"
      className="grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-3"
    >
      <Stat label="Credits that count" value={applicable_credits} testId="history-applicable">
        Completed UMD courses and verified transfer credit
      </Stat>
      <Stat label="Credits recorded" value={earned_credits} testId="history-earned">
        Everything completed, verified or not
      </Stat>
      <Stat label="In progress" value={in_progress_credits} testId="history-in-progress">
        Counts once completed
      </Stat>
      {pending.length > 0 && (
        <div className="bg-amber-50 p-4 text-sm text-amber-900 sm:col-span-3" data-testid="pending">
          <p className="font-semibold">Not counted yet ({pending.length})</p>
          <ul className="mt-1 list-disc pl-5">
            {pending.map((p, i) => (
              <li key={i}>
                {p.description}
                {p.credits ? ` (${p.credits} cr)` : ""}: {p.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, testId, children }: { label: string; value: number; testId: string; children: React.ReactNode }) {
  return (
    <div className="bg-white p-4">
      <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{label}</p>
      <p className="mt-1 text-2xl font-bold" data-testid={testId}>
        {value}
      </p>
      <p className="mt-0.5 text-xs text-slate-500">{children}</p>
    </div>
  );
}

// --- Semesters --------------------------------------------------------------------

function termOptions(): string[] {
  const year = new Date().getFullYear();
  const out: string[] = [];
  for (let y = year + 1; y >= year - 12; y--) {
    for (const season of ["Fall", "Summer", "Spring", "Winter"]) out.push(`${season} ${y}`);
  }
  return out;
}

function AddTermForm({ actions }: { actions: Actions }) {
  const [term, setTerm] = useState("");
  const [atUmd, setAtUmd] = useState(true);
  const [institution, setInstitution] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!term || (!atUmd && !institution.trim())) return;
    const ok = await actions.run(() =>
      addHistoryTerm(actions.sessionId, { term, at_umd: atUmd, institution: atUmd ? null : institution.trim() }),
    );
    if (ok) {
      setTerm("");
      setInstitution("");
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Add a semester"
      className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm"
    >
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Semester</span>
        <select id="new-term" value={term} onChange={(e) => setTerm(e.target.value)} className={inputClass}>
          <option value="">Choose…</option>
          {termOptions().map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">School</span>
        <select
          id="new-term-school"
          value={atUmd ? "umd" : "other"}
          onChange={(e) => setAtUmd(e.target.value === "umd")}
          className={inputClass}
        >
          <option value="umd">UMD (College Park)</option>
          <option value="other">Another school</option>
        </select>
      </label>
      {!atUmd && (
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">School name</span>
          <input
            id="new-term-institution"
            value={institution}
            maxLength={200}
            onChange={(e) => setInstitution(e.target.value)}
            placeholder="e.g. Montgomery College"
            className={inputClass}
          />
        </label>
      )}
      <button type="submit" disabled={actions.busy || !term || (!atUmd && !institution.trim())} className={primaryButton}>
        Add semester
      </button>
    </form>
  );
}

function TermSection({ term, actions }: { term: HistoryTerm; actions: Actions }) {
  const [editing, setEditing] = useState(false);
  const [draftTerm, setDraftTerm] = useState(term.term);
  const [draftInstitution, setDraftInstitution] = useState(term.institution);
  const badge = {
    past: "bg-slate-100 text-slate-700",
    current: "bg-amber-100 text-amber-900",
    future: "bg-sky-100 text-sky-900",
  }[term.period];

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-5" data-history-term={term.term}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {editing ? (
          <>
            <select
              aria-label="Semester"
              value={draftTerm}
              onChange={(e) => setDraftTerm(e.target.value)}
              className={inputClass}
            >
              {[...new Set([term.term, ...termOptions()])].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            {!term.at_umd && (
              <input
                aria-label="School name"
                value={draftInstitution}
                maxLength={200}
                onChange={(e) => setDraftInstitution(e.target.value)}
                className={inputClass}
              />
            )}
            <button
              type="button"
              disabled={actions.busy}
              onClick={async () => {
                const ok = await actions.run(() =>
                  updateHistoryTerm(actions.sessionId, term.id, {
                    term: draftTerm,
                    ...(term.at_umd ? {} : { institution: draftInstitution.trim() }),
                  }),
                );
                if (ok) setEditing(false);
              }}
              className={primaryButton}
            >
              Save
            </button>
            <button type="button" onClick={() => setEditing(false)} className={linkButton}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <h3 className="text-base font-semibold">{term.term}</h3>
            <span className="text-sm text-slate-600">{term.institution}</span>
            <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${badge}`}>
              {term.period === "current" ? "In progress" : term.period === "past" ? "Completed" : "Upcoming"}
            </span>
            <span className="flex-1" />
            <button type="button" onClick={() => setEditing(true)} className={linkButton}>
              Edit
            </button>
            <button
              type="button"
              disabled={actions.busy}
              onClick={() =>
                confirm(`Remove ${term.term} and everything recorded in it?`) &&
                actions.run(() => removeHistoryTerm(actions.sessionId, term.id))
              }
              className={`${linkButton} hover:text-red-700`}
              aria-label={`Remove ${term.term} at ${term.institution}`}
            >
              Remove
            </button>
          </>
        )}
      </div>

      {term.at_umd ? (
        <>
          <CourseList courses={term.courses} actions={actions} />
          <AddUmdCourse termId={term.id} defaultStatus={term.period === "past" ? "completed" : "in_progress"} actions={actions} />
        </>
      ) : (
        <>
          <TransferList transfers={term.transfers} actions={actions} />
          <AddTransferForm termId={term.id} institution={term.institution} actions={actions} />
        </>
      )}
    </li>
  );
}

// --- UMD courses ------------------------------------------------------------------

function CourseList({ courses, actions, terms }: { courses: HistoryCourse[]; actions: Actions; terms?: HistoryTerm[] }) {
  if (courses.length === 0) return <p className="mt-3 text-sm text-slate-500">No courses recorded.</p>;
  return (
    <ul className="mt-3 divide-y divide-slate-100 text-sm">
      {courses.map((c) => (
        <li key={c.code} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2" data-history-course={c.code}>
          <span className="min-w-0 flex-1">
            <span className="font-medium">{c.code}</span> <span className="text-slate-600">{c.name}</span>{" "}
            <span className="text-slate-400">· {c.credits} cr</span>
          </span>
          <select
            aria-label={`Status of ${c.code}`}
            value={c.status}
            disabled={actions.busy}
            onChange={(e) =>
              actions.run(() =>
                updateCompletedCourse(actions.sessionId, c.code, {
                  status: e.target.value as CourseStatus,
                  ...(e.target.value === "in_progress" ? { grade: null } : {}),
                }),
              )
            }
            className={smallSelect}
          >
            <option value="completed">Completed</option>
            <option value="in_progress">In progress</option>
          </select>
          {c.status === "completed" && (
            <select
              aria-label={`Grade for ${c.code}`}
              value={c.grade ?? ""}
              disabled={actions.busy}
              onChange={(e) => actions.run(() => updateCompletedCourse(actions.sessionId, c.code, { grade: e.target.value || null }))}
              className={smallSelect}
            >
              <option value="">Grade</option>
              {GRADES.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          )}
          {terms && terms.length > 0 && (
            <select
              aria-label={`Semester for ${c.code}`}
              value=""
              disabled={actions.busy}
              onChange={(e) =>
                e.target.value &&
                actions.run(() =>
                  updateCompletedCourse(actions.sessionId, c.code, { academic_term_id: Number(e.target.value) }),
                )
              }
              className={smallSelect}
            >
              <option value="">Move to semester…</option>
              {terms.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.term}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            disabled={actions.busy}
            onClick={() => actions.run(() => removeCompletedCourse(actions.sessionId, c.code))}
            className={`${linkButton} hover:text-red-700`}
            aria-label={`Remove ${c.code}`}
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}

function AddUmdCourse({ termId, defaultStatus, actions }: { termId: number; defaultStatus: CourseStatus; actions: Actions }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<CourseStatus>(defaultStatus);
  const { results } = useCourseSearch(search, { limit: 6 });

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-2 text-sm font-medium text-red-700 hover:underline">
        + Add a UMD course
      </button>
    );
  }
  return (
    <div className="mt-3 rounded-lg border border-slate-200 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          autoFocus
          aria-label="Search UMD courses"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by code or name"
          className={`${inputClass} min-w-0 flex-1`}
        />
        <select
          aria-label="Course status"
          value={status}
          onChange={(e) => setStatus(e.target.value as CourseStatus)}
          className={inputClass}
        >
          <option value="completed">Completed</option>
          <option value="in_progress">In progress</option>
        </select>
        <button type="button" onClick={() => setOpen(false)} className={linkButton}>
          Done
        </button>
      </div>
      {(results ?? []).length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100" data-testid="history-search-results">
          {(results ?? []).map((c) => (
            <li key={c.code} className="flex items-center gap-3 py-1.5">
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{c.code}</span> <span className="text-slate-600">{c.name}</span>{" "}
                <span className="text-slate-400">· {formatCredits(c)}</span>
              </span>
              <button
                type="button"
                disabled={actions.busy}
                onClick={async () => {
                  if (await actions.run(() => addCompletedCourse(actions.sessionId, c.code, { status, academic_term_id: termId }))) {
                    setSearch("");
                  }
                }}
                className={smallPrimary}
              >
                Add
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Transfer credit ----------------------------------------------------------------

function TransferList({ transfers, actions }: { transfers: TransferCredit[]; actions: Actions }) {
  if (transfers.length === 0) return <p className="mt-3 text-sm text-slate-500">No credit recorded.</p>;
  return (
    <ul className="mt-3 divide-y divide-slate-100 text-sm">
      {transfers.map((x) => (
        <li key={x.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2" data-transfer={x.external_code ?? x.title ?? ""}>
          <span className="min-w-0 flex-1">
            <span className="font-medium">{x.external_code ?? (x.kind === "credits" ? "Credit" : "")}</span>{" "}
            <span className="text-slate-600">{x.title}</span> <span className="text-slate-400">· {x.credits} cr</span>
            {x.grade && <span className="text-slate-400"> · {x.grade}</span>}
            {x.status === "in_progress" && <span className="ml-1 text-xs text-amber-800">(in progress)</span>}
            <span className="block text-xs text-slate-500">
              {x.equivalent_code
                ? `UMD equivalent: ${x.equivalent_code}${x.equivalent_name ? ` ${x.equivalent_name}` : ""}`
                : x.kind === "credits"
                  ? "Doesn't map to one UMD course; counts toward total credits only"
                  : "No UMD equivalent recorded; counts toward total credits only"}
            </span>
            <span
              data-testid="transfer-status"
              className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                x.counted ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"
              }`}
            >
              {x.counted ? "Counted" : x.status === "in_progress" ? "In progress, not counted yet" : "Not counted until verified"}
            </span>
          </span>
          <select
            aria-label={`Verification for ${x.external_code ?? x.title ?? "credit"}`}
            value={x.verification}
            disabled={actions.busy}
            onChange={(e) =>
              actions.run(() => updateTransfer(actions.sessionId, x.id, { verification: e.target.value as TransferVerification }))
            }
            className={smallSelect}
          >
            <option value="student_reported">Reported by me</option>
            <option value="umd_verified">Verified by UMD</option>
          </select>
          <button
            type="button"
            disabled={actions.busy}
            onClick={() => actions.run(() => removeTransfer(actions.sessionId, x.id))}
            className={`${linkButton} hover:text-red-700`}
            aria-label={`Remove ${x.external_code ?? x.title ?? "credit"}`}
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}

function AddTransferForm({ termId, institution, actions }: { termId: number | null; institution?: string; actions: Actions }) {
  const empty = {
    kind: "course" as "course" | "credits",
    institution: "",
    external_code: "",
    title: "",
    credits: "3",
    grade: "",
    status: "completed" as CourseStatus,
    equivalent_code: "",
    verification: "student_reported" as TransferVerification,
  };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const set = (changes: Partial<typeof empty>) => setForm({ ...form, ...changes });

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-2 text-sm font-medium text-red-700 hover:underline">
        + Add {termId === null ? "credit without a semester (AP, IB, exam…)" : "a course or credit"}
      </button>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body: TransferInput = {
      academic_term_id: termId,
      institution: termId === null ? form.institution.trim() || null : institution,
      kind: form.kind,
      external_code: form.external_code.trim() || null,
      title: form.title.trim() || null,
      credits: Number(form.credits),
      grade: form.status === "completed" ? form.grade.trim() || null : null,
      status: form.status,
      equivalent_code: form.kind === "course" ? form.equivalent_code.trim() || null : null,
      verification: form.verification,
    };
    if (await actions.run(() => addTransfer(actions.sessionId, body))) {
      setForm(empty);
      setOpen(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label="Add transfer credit" className="mt-3 grid gap-3 rounded-lg border border-slate-200 p-3 text-sm sm:grid-cols-3">
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Type</span>
        <select aria-label="Type" value={form.kind} onChange={(e) => set({ kind: e.target.value as "course" | "credits" })} className={inputClass}>
          <option value="course">A course</option>
          <option value="credits">Credits not tied to one course</option>
        </select>
      </label>
      {termId === null && (
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">Source</span>
          <input
            aria-label="Source"
            required
            value={form.institution}
            maxLength={200}
            onChange={(e) => set({ institution: e.target.value })}
            placeholder="e.g. AP exam, Montgomery College"
            className={inputClass}
          />
        </label>
      )}
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Course code</span>
        <input
          aria-label="Course code at that school"
          value={form.external_code}
          maxLength={30}
          onChange={(e) => set({ external_code: e.target.value })}
          placeholder="e.g. ENGL 101"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Title</span>
        <input
          aria-label="Title"
          value={form.title}
          maxLength={200}
          onChange={(e) => set({ title: e.target.value })}
          placeholder={form.kind === "credits" ? "e.g. Lower-level electives" : "e.g. English Composition"}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Credits</span>
        <input
          aria-label="Credits"
          type="number"
          min={0}
          max={200}
          required
          value={form.credits}
          onChange={(e) => set({ credits: e.target.value })}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Status</span>
        <select aria-label="Transfer status" value={form.status} onChange={(e) => set({ status: e.target.value as CourseStatus })} className={inputClass}>
          <option value="completed">Completed</option>
          <option value="in_progress">In progress</option>
        </select>
      </label>
      {form.status === "completed" && (
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">Grade (optional)</span>
          <input aria-label="Grade" value={form.grade} maxLength={10} onChange={(e) => set({ grade: e.target.value })} className={inputClass} />
        </label>
      )}
      {form.kind === "course" && (
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">UMD equivalent (if known)</span>
          <input
            aria-label="UMD equivalent"
            value={form.equivalent_code}
            maxLength={10}
            onChange={(e) => set({ equivalent_code: e.target.value })}
            placeholder="e.g. ENGL101"
            className={inputClass}
          />
        </label>
      )}
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Verification</span>
        <select
          aria-label="Verification"
          value={form.verification}
          onChange={(e) => set({ verification: e.target.value as TransferVerification })}
          className={inputClass}
        >
          <option value="student_reported">Reported by me (not counted)</option>
          <option value="umd_verified">Verified by UMD (on my UMD record)</option>
        </select>
      </label>
      <div className="flex items-end gap-2 sm:col-span-3">
        <button type="submit" disabled={actions.busy} className={primaryButton}>
          Save credit
        </button>
        <button type="button" onClick={() => setOpen(false)} className={linkButton}>
          Cancel
        </button>
        <p className="text-xs text-slate-500">
          Equivalencies aren&apos;t looked up: enter one only if UMD has told you (e.g. Transfer Credit Services).
        </p>
      </div>
    </form>
  );
}

// --- Items without a semester -------------------------------------------------------

function Unassigned({ history, actions }: { history: History; actions: Actions }) {
  const umdTerms = history.terms.filter((t) => t.at_umd);
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-lg font-semibold">Not tied to a semester</h2>
      <p className="mt-1 text-sm text-slate-500">
        UMD courses added without a semester (e.g. from your Profile), and credit like AP or IB exams.
      </p>
      {history.unassigned_courses.length > 0 && (
        <>
          <h3 className="mt-4 text-sm font-semibold text-slate-700">UMD courses</h3>
          <CourseList courses={history.unassigned_courses} actions={actions} terms={umdTerms} />
        </>
      )}
      <h3 className="mt-4 text-sm font-semibold text-slate-700">Other credit</h3>
      <TransferList transfers={history.unassigned_transfers} actions={actions} />
      <AddTransferForm termId={null} actions={actions} />
    </section>
  );
}

// --- Requirements met another way -----------------------------------------------------

function Fulfillments({ history, actions }: { history: History; actions: Actions }) {
  const [key, setKey] = useState("");
  const [method, setMethod] = useState<FulfillmentMethod>("transfer_credit");
  const [verification, setVerification] = useState<FulfillmentVerification>("student_reported");
  const [note, setNote] = useState("");
  const taken = new Set(history.fulfillments.map((f) => f.requirement_key));
  const options = history.requirement_options.filter((o) => !taken.has(o.key));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!key) return;
    const ok = await actions.run(() =>
      addFulfillment(actions.sessionId, { requirement_key: key, method, verification, note: note.trim() || null }),
    );
    if (ok) {
      setKey("");
      setNote("");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-lg font-semibold">Requirements met another way</h2>
      <p className="mt-1 text-sm text-slate-500">
        For example, Gen Ed completed through an associate degree, or a requirement waived. Only items verified by UMD
        or approved as an exception count; a requirement counts once, however it was met.
      </p>

      {history.fulfillments.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {history.fulfillments.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2" data-fulfillment={f.requirement_key}>
              <span className="min-w-0 flex-1">
                <span className="font-medium">{f.requirement_name}</span>{" "}
                <span className="text-slate-500">· {METHODS[f.method]}</span>
                {f.note && <span className="block text-xs text-slate-500">{f.note}</span>}
                <span
                  data-testid="fulfillment-status"
                  className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                    f.counted ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"
                  }`}
                >
                  {f.counted ? "Counted" : "Not counted until verified"}
                </span>
              </span>
              <select
                aria-label={`Verification for ${f.requirement_name}`}
                value={f.verification}
                disabled={actions.busy}
                onChange={(e) =>
                  actions.run(() =>
                    updateFulfillment(actions.sessionId, f.id, { verification: e.target.value as FulfillmentVerification }),
                  )
                }
                className={smallSelect}
              >
                {Object.entries(VERIFICATION).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={actions.busy}
                onClick={() => actions.run(() => removeFulfillment(actions.sessionId, f.id))}
                className={`${linkButton} hover:text-red-700`}
                aria-label={`Remove ${f.requirement_name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} aria-label="Record a requirement" className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="font-medium text-slate-700">Requirement</span>
          <select id="fulfillment-requirement" value={key} onChange={(e) => setKey(e.target.value)} className={inputClass}>
            <option value="">Choose…</option>
            {options.map((o) => (
              <option key={o.key} value={o.key}>
                {[...o.path.slice(1), o.name].join(" › ")}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">How</span>
          <select aria-label="How it was met" value={method} onChange={(e) => setMethod(e.target.value as FulfillmentMethod)} className={inputClass}>
            {Object.entries(METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">Verification</span>
          <select
            aria-label="Fulfillment verification"
            value={verification}
            onChange={(e) => setVerification(e.target.value as FulfillmentVerification)}
            className={inputClass}
          >
            {Object.entries(VERIFICATION).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="font-medium text-slate-700">Note (optional)</span>
          <input
            aria-label="Note"
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Approved by advisor, April 2026"
            className={inputClass}
          />
        </label>
        <div>
          <button type="submit" disabled={actions.busy || !key} className={primaryButton}>
            Record requirement
          </button>
        </div>
      </form>
    </section>
  );
}

const inputClass =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-red-700 focus:outline-none focus:ring-1 focus:ring-red-700";
const smallSelect = "rounded-md border border-slate-300 bg-white px-1.5 py-1 text-xs disabled:opacity-50";
const primaryButton =
  "rounded-lg bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50";
const smallPrimary =
  "shrink-0 rounded-md bg-red-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-50";
const linkButton = "text-sm text-slate-500 hover:text-slate-800 disabled:opacity-50";


