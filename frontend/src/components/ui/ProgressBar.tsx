type Segment = { value: number; className: string; label: string };

// A horizontal bar made of one or more filled segments out of `max`.
export default function ProgressBar({
  segments,
  max,
  label,
  size = "md",
}: {
  segments: Segment[];
  max: number;
  label: string;
  size?: "sm" | "md";
}) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={total}
      className={`flex w-full overflow-hidden rounded-full bg-slate-100 ${size === "sm" ? "h-1.5" : "h-2.5"}`}
    >
      {segments.map((s) => (
        <div
          key={s.label}
          title={`${s.label}: ${s.value}`}
          className={s.className}
          style={{ width: `${Math.min((s.value / Math.max(max, 1)) * 100, 100)}%` }}
        />
      ))}
    </div>
  );
}
