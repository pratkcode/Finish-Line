import type { RequirementStatus } from "@/lib/api";

const STYLES: Record<RequirementStatus, { symbol: string; className: string; label: string }> = {
  complete: { symbol: "✓", className: "bg-emerald-600 text-white", label: "Complete" },
  in_progress: { symbol: "◐", className: "bg-amber-100 text-amber-700", label: "In progress" },
  not_started: { symbol: "", className: "border-2 border-slate-300 bg-white", label: "Not started" },
  not_tracked: { symbol: "–", className: "bg-slate-100 text-slate-400", label: "Not tracked yet" },
};

export default function StatusIcon({ status }: { status: RequirementStatus }) {
  const { symbol, className, label } = STYLES[status];
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${className}`}
    >
      {symbol}
    </span>
  );
}

export const STATUS_LABELS = Object.fromEntries(
  Object.entries(STYLES).map(([status, style]) => [status, style.label]),
) as Record<RequirementStatus, string>;
