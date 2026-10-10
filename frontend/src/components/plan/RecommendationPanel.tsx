import type { Recommendation } from "@/lib/api";

type Props = {
  recommendation: Recommendation;
  busy: boolean;
  onAccept: () => void;
  onDismiss: () => void;
};

// A generated plan the student can review. Nothing is saved until they accept.
export default function RecommendationPanel({ recommendation, busy, onAccept, onDismiss }: Props) {
  const { additions, slots } = recommendation;
  const byTerm = new Map<string, typeof additions>();
  for (const c of [...additions, ...slots]) byTerm.set(c.term, [...(byTerm.get(c.term) ?? []), c]);
  const credits = additions.reduce((n, c) => n + c.credits, 0);

  return (
    <section
      aria-label="Recommended plan"
      className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">Recommended plan (not saved)</p>
          <p className="mt-1 max-w-2xl">
            Built around the courses already in your plan. It&apos;s a suggestion, not an official
            UMD schedule. Add it to your plan, then change anything you like.
          </p>
          <p className="mt-1">
            Would graduate: <span className="font-semibold">{recommendation.projected_graduation ?? "can't tell yet"}</span>
            {" · "}adds {additions.length} {additions.length === 1 ? "course" : "courses"} ({credits} credits)
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onDismiss}
            disabled={busy}
            className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-medium hover:bg-amber-100 disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={busy || additions.length === 0}
            className="rounded-lg bg-slate-900 px-3 py-1.5 font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Add {additions.length} {additions.length === 1 ? "course" : "courses"} to my plan
          </button>
        </div>
      </div>

      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {[...byTerm.entries()].map(([term, courses]) => (
          <li key={term} className="rounded-lg bg-white/70 p-3">
            <p className="font-semibold">{term}</p>
            <ul className="mt-1 space-y-0.5">
              {courses.map((c, i) => (
                <li key={`${c.code ?? c.name}-${i}`} className={c.code ? "" : "text-amber-800 italic"}>
                  {c.code ? (
                    <>
                      <span className="font-medium">{c.code}</span> {c.name}
                    </>
                  ) : (
                    <>{c.name} (you choose)</>
                  )}{" "}
                  <span className="text-amber-700">· {c.credits} cr</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {slots.length > 0 && (
        <p className="mt-3 text-xs">
          Italic lines are requirements where you pick the course. They aren&apos;t added; search for a course in
          that semester when you&apos;re ready.
        </p>
      )}
      {recommendation.unscheduled.length > 0 && (
        <p className="mt-2 text-xs">Couldn&apos;t place: {recommendation.unscheduled.join("; ")}</p>
      )}
    </section>
  );
}
