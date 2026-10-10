import type { StudentPlan } from "@/lib/api";

// Totals for the saved plan. Every number comes from the API, which computes
// them from the courses currently saved in the plan.
export default function PlanSummary({ plan }: { plan: StudentPlan }) {
  const { completed, in_progress, planned, remaining, required, unverified } = plan.credits;
  const loads = plan.terms.map((t) => t.credits);

  return (
    <section
      aria-label="Plan summary"
      className="grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-3"
    >
      <Stat label="Projected graduation">
        <span data-testid="projected-graduation" className={plan.projected_graduation ? "" : "text-slate-400"}>
          {plan.projected_graduation ?? "Not yet"}
        </span>
        <Sub>{plan.graduation_note}</Sub>
      </Stat>

      <Stat label="Credits">
        <span data-testid="planned-credits">{planned}</span>
        <span className="text-xl font-medium text-slate-400"> planned</span>
        <Sub>
          <span data-testid="completed-credits">{completed}</span> completed ·{" "}
          {in_progress > 0 && (
            <>
              <span data-testid="in-progress-credits">{in_progress}</span> in progress ·{" "}
            </>
          )}
          <span data-testid="remaining-credits">{remaining ?? "?"}</span> still to plan
          {required !== null && <> of {required}</>}
          {unverified > 0 && (
            <span className="block text-amber-800">{unverified} more not counted until verified</span>
          )}
        </Sub>
      </Stat>

      <Stat label="Current plan">
        <span className="text-xl sm:text-2xl" aria-label={`Credits per semester: ${loads.join(", ")}`}>
          {loads.length ? loads.join(" → ") : "—"}
        </span>
        <Sub>
          {loads.length} {loads.length === 1 ? "semester" : "semesters"} from {plan.plan_start_term} · up to{" "}
          {plan.max_credits_per_term} credits each
          {plan.include_summer && <> ({plan.max_summer_credits ?? plan.max_credits_per_term} in Summer)</>}
        </Sub>
      </Stat>
    </section>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface p-5">
      <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{label}</p>
      <div className="mt-1.5 text-3xl font-bold tracking-tight text-slate-900">{children}</div>
    </div>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-sm font-normal tracking-normal text-slate-500">{children}</p>;
}
