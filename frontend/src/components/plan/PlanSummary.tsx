import type { GraduationPlan } from "@/lib/api";

type Props = {
  plan: GraduationPlan;
  before?: string | null; // graduation in the saved plan, when showing a what-if
  draft: boolean;
};

export default function PlanSummary({ plan, before, draft }: Props) {
  const { remaining, completed, required } = plan.credits;
  const loads = plan.terms.map((t) => t.credits);
  const changedGraduation = draft && before !== undefined && before !== plan.projected_graduation;

  return (
    <section className="grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-3">
      <Stat label="Projected graduation">
        <span className={plan.projected_graduation ? "" : "text-slate-400"}>
          {plan.projected_graduation ?? "Not yet"}
        </span>
        <Sub>
          {changedGraduation ? (
            <>
              Was {before ?? "not projected"} · <span className="text-amber-700">what-if</span>
            </>
          ) : (
            plan.graduation_note
          )}
        </Sub>
      </Stat>

      <Stat label="Credits remaining">
        {remaining}
        <Sub>
          {completed} of {required ?? "?"} earned · {plan.credits.planned} planned
        </Sub>
      </Stat>

      <Stat label="Current plan">
        <span className="text-xl sm:text-2xl" aria-label={`Credits per semester: ${loads.join(", ")}`}>
          {loads.length ? loads.join(" → ") : "—"}
        </span>
        <Sub>
          {loads.length} {loads.length === 1 ? "semester" : "semesters"} from {plan.start_term} ·
          up to {plan.max_credits_per_term} credits each
        </Sub>
      </Stat>
    </section>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-white p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <div className="mt-1.5 text-3xl font-bold tracking-tight text-slate-900">{children}</div>
    </div>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-sm font-normal tracking-normal text-slate-500">{children}</p>;
}
