import Link from "next/link";
import type { HistoryTerm } from "@/lib/api";

// Past and current semesters, from the academic history. Read-only here;
// they're edited on the Academic History page.
export default function HistoryTimeline({ history, currentTerm }: { history: HistoryTerm[]; currentTerm: string }) {
  const past = history.filter((t) => t.period === "past");
  const current = history.filter((t) => t.period === "current");

  return (
    <section aria-label="Academic history">
      <h2 className="mb-3 text-sm font-semibold tracking-wider text-slate-500 uppercase">History</h2>
      {history.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-surface px-5 py-3 text-sm text-slate-600">
          No semesters recorded yet.{" "}
          <Link href="/history" className="underline">
            Add your past semesters and current courses
          </Link>{" "}
          (at UMD or elsewhere) so they show here.
        </p>
      ) : (
        <ol className="space-y-2">
          {past.length > 0 && (
            <li>
              <details className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-3 text-sm">
                <summary className="cursor-pointer font-medium text-slate-700">
                  {past.length} past {past.length === 1 ? "semester" : "semesters"} ({past[0].term} – {past.at(-1)!.term})
                </summary>
                <ul className="mt-2 space-y-2">
                  {past.map((t) => (
                    <TermLine key={t.id} term={t} />
                  ))}
                </ul>
              </details>
            </li>
          )}
          {current.map((t) => (
            <li
              key={t.id}
              data-testid="current-term"
              className="rounded-xl border border-amber-300 bg-amber-50 px-5 py-3 text-sm"
            >
              <p className="font-semibold text-amber-950">
                {t.term} · in progress <span className="font-normal text-amber-800">({t.institution})</span>
              </p>
              <TermCourses term={t} />
            </li>
          ))}
          {current.length === 0 && (
            <li className="px-1 text-sm text-slate-500">
              Current semester: {currentTerm} (no courses recorded as in progress).
            </li>
          )}
        </ol>
      )}
    </section>
  );
}

function TermLine({ term }: { term: HistoryTerm }) {
  return (
    <li>
      <p className="font-medium text-slate-800">
        {term.term} <span className="font-normal text-slate-500">· {term.institution}</span>
      </p>
      <TermCourses term={term} />
    </li>
  );
}

function TermCourses({ term }: { term: HistoryTerm }) {
  const items = [
    ...term.courses.map((c) => `${c.code}${c.status === "in_progress" ? " (in progress)" : c.grade ? ` (${c.grade})` : ""}`),
    ...term.transfers.map(
      (x) =>
        `${x.external_code ?? x.title ?? "Credit"} · ${x.credits} cr${x.equivalent_code ? ` → ${x.equivalent_code}` : ""}${
          x.counted ? "" : x.status === "in_progress" ? " (in progress)" : " (not verified)"
        }`,
    ),
  ];
  return (
    <p className="mt-0.5 text-slate-600">{items.length ? items.join(", ") : "No courses recorded."}</p>
  );
}
