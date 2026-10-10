import { nextTerm, type SessionChanges, type StudentPlan } from "@/lib/api";

type Props = {
  plan: StudentPlan;
  busy: boolean;
  onSave: (changes: SessionChanges) => void;
};

const ALL_SEASONS = ["Spring", "Summer", "Fall"];

// Upcoming terms after `term`, for the choosers.
function upcoming(term: string, count: number): string[] {
  const out: string[] = [];
  for (let t = nextTerm(term, ALL_SEASONS); out.length < count; t = nextTerm(t, ALL_SEASONS)) out.push(t);
  return out;
}

// When the plan starts, whether it uses Summer, and the target graduation.
// Each change is saved right away.
export default function PlanSettings({ plan, busy, onSave }: Props) {
  const starts = [plan.current_term, ...upcoming(plan.current_term, 9)].filter(
    (t) => !t.startsWith("Winter"),
  );
  if (!starts.includes(plan.plan_start_term)) starts.push(plan.plan_start_term);
  const targets = upcoming(plan.current_term, 24);
  if (plan.target_graduation_term && !targets.includes(plan.target_graduation_term)) {
    targets.push(plan.target_graduation_term);
  }

  return (
    <section
      aria-label="Plan settings"
      className="flex flex-wrap items-end gap-x-6 gap-y-3 rounded-xl border border-slate-200 bg-white p-4 text-sm"
    >
      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">First semester to plan</span>
        <select
          id="plan-start"
          value={plan.plan_start_term}
          disabled={busy}
          onChange={(e) => onSave({ plan_start_term: e.target.value })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 disabled:opacity-50"
        >
          {starts.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 pb-1.5">
        <input
          id="include-summer"
          type="checkbox"
          checked={plan.include_summer}
          disabled={busy}
          onChange={(e) => onSave({ include_summer: e.target.checked })}
        />
        <span className="text-slate-700">Plan Summer terms</span>
      </label>

      {plan.include_summer && (
        <label className="flex flex-col gap-1">
          <span className="font-medium text-slate-700">Summer credit limit</span>
          <select
            id="summer-credits"
            value={plan.max_summer_credits ?? plan.max_credits_per_term}
            disabled={busy}
            onChange={(e) => onSave({ max_summer_credits: Number(e.target.value) })}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 disabled:opacity-50"
          >
            {Array.from({ length: 18 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n} credits
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="flex flex-col gap-1">
        <span className="font-medium text-slate-700">Target graduation</span>
        <select
          id="target-graduation"
          value={plan.target_graduation_term ?? ""}
          disabled={busy}
          onChange={(e) => onSave({ target_graduation_term: e.target.value || null })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 disabled:opacity-50"
        >
          <option value="">No target</option>
          {targets.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      {plan.target && (
        <p
          data-testid="target-check"
          className={`pb-1.5 ${
            plan.target.meets === false ? "text-red-700" : plan.target.meets ? "text-emerald-700" : "text-slate-500"
          }`}
        >
          {plan.target.message}
        </p>
      )}
    </section>
  );
}
