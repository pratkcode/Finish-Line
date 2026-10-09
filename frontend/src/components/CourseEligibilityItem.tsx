import {
  formatCredits,
  type CourseEligibility,
  type EligibilityStatus,
  type PrerequisiteGroupState,
  type PrerequisiteOptionState,
} from "@/lib/api";

const STATUS: Record<EligibilityStatus, { label: string; className: string }> = {
  available: { label: "Available now", className: "bg-emerald-50 text-emerald-700" },
  available_with_concurrent: {
    label: "Available with a same-semester course",
    className: "bg-amber-50 text-amber-800",
  },
  blocked: { label: "Not currently available", className: "bg-red-50 text-red-700" },
  completed: { label: "Completed", className: "bg-slate-100 text-slate-600" },
};

// One remaining course; expands to show its prerequisites.
export default function CourseEligibilityItem({ course }: { course: CourseEligibility }) {
  const status = STATUS[course.status];
  return (
    <li>
      <details className="group rounded-lg border border-slate-200">
        <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2 text-sm hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
          <span className="h-4 w-4 shrink-0 rounded-full border-2 border-slate-300" />
          <span className="min-w-0 flex-1">
            <span className="font-medium">{course.code}</span>{" "}
            <span className="text-slate-600">{course.name}</span>
          </span>
          <span
            className={`hidden shrink-0 rounded px-2 py-0.5 text-xs font-medium sm:inline ${status.className}`}
          >
            {status.label}
          </span>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium sm:hidden ${status.className}`}
            aria-label={status.label}
          >
            {course.status === "blocked" ? "✗" : "✓"}
          </span>
          <span className="shrink-0 text-xs text-slate-400 transition-transform group-open:rotate-90">
            ▶
          </span>
        </summary>

        <div className="space-y-3 border-t border-slate-100 px-3 py-3 text-sm">
          <p className="text-slate-500">
            {formatCredits(course)}
            {course.retake && " · Retake: your earlier grade was below the minimum"}
          </p>

          <div>
            <p className="font-medium text-slate-700">
              {course.groups.some((g) => g.state === "missing") ? "Missing" : "Prerequisites"}
            </p>
            {course.groups.length === 0 ? (
              <p className="mt-1 text-slate-500">None</p>
            ) : (
              <ul className="mt-1 space-y-1.5">
                {course.groups.map((group, i) => (
                  <GroupRow key={i} group={group} />
                ))}
              </ul>
            )}
          </div>

          {course.complete_first.length > 0 && (
            <p className="text-slate-700">
              <span className="font-medium">Complete first:</span>{" "}
              {course.complete_first.map((c) => c.code).join(" → ")}
            </p>
          )}
          {course.take_with.length > 0 && (
            <p className="text-slate-700">
              <span className="font-medium">Take the same semester (or earlier):</span>{" "}
              {course.take_with.map((c) => c.code).join(", ")}
            </p>
          )}
          {course.additional_conditions && (
            <p className="rounded bg-amber-50 px-3 py-2 text-amber-900">
              Also check: {course.additional_conditions}
            </p>
          )}
        </div>
      </details>
    </li>
  );
}

function GroupRow({ group }: { group: PrerequisiteGroupState }) {
  const notes = [
    group.min_grade && `${group.min_grade} or better`,
    group.timing === "before_or_concurrent" && "or take the same semester",
    group.timing === "concurrent" && "take the same semester",
  ].filter(Boolean);

  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {group.options.length > 1 && <span className="text-slate-500">One of:</span>}
      {group.options.map((option) => (
        <OptionChip key={option.code} option={option} groupState={group.state} />
      ))}
      {notes.length > 0 && <span className="text-xs text-slate-400">({notes.join(", ")})</span>}
    </li>
  );
}

function OptionChip({
  option,
  groupState,
}: {
  option: PrerequisiteOptionState;
  groupState: PrerequisiteGroupState["state"];
}) {
  let icon = "✗";
  let className = "text-red-700";
  let detail = "";
  if (option.state === "completed") {
    icon = "✓";
    className = "text-emerald-700";
  } else if (groupState === "met") {
    // Another option already satisfies this group.
    icon = "–";
    className = "text-slate-400";
  } else if (option.state === "low_grade") {
    detail = ` (earned ${option.grade})`;
  } else if (option.state === "available") {
    detail = " (available now)";
  }

  return (
    <span className={`inline-flex items-center gap-1 ${className}`} title={option.name}>
      <span aria-hidden className="font-bold">
        {icon}
      </span>
      <span className="sr-only">{icon === "✓" ? "Completed:" : icon === "✗" ? "Missing:" : "Not needed:"}</span>
      <span className="font-medium">{option.code}</span>
      {detail && <span className="text-xs text-slate-500">{detail}</span>}
    </span>
  );
}
