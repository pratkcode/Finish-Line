import StatusIcon from "@/components/StatusIcon";
import type { CourseFilter, Requirement } from "@/lib/api";

type Props = {
  requirement: Requirement;
};

// One requirement in the checklist. Groups render their children recursively.
export default function RequirementItem({ requirement }: Props) {
  const { progress, rule, children } = requirement;
  if (!progress) return null;
  const isGroup = rule === "all_children" || rule === "any_child";

  return (
    <li>
      <div className="flex items-start gap-3">
        <StatusIcon status={progress.status} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{requirement.name}</span>
            {requirement.optional && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                Optional
              </span>
            )}
            <span className="text-sm text-slate-500">{summary(requirement)}</span>
          </div>
          {requirement.description && (
            <p className="mt-0.5 text-sm text-slate-500">{requirement.description}</p>
          )}
        </div>
      </div>

      <div className="ml-8">
        {isGroup ? (
          <>
            {rule === "any_child" && (
              <p className="mt-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                Complete one of:
              </p>
            )}
            <ul className="mt-3 space-y-4 border-l border-slate-200 pl-4">
              {children.map((child) => (
                <RequirementItem key={child.key} requirement={child} />
              ))}
            </ul>
          </>
        ) : (
          <CourseChecklist requirement={requirement} />
        )}
      </div>
    </li>
  );
}

function CourseChecklist({ requirement }: Props) {
  const { rule, progress, courses, filters, eligible_courses, eligible_count } = requirement;
  if (!progress || rule === "not_tracked") return null;

  const applied = new Map(progress.applied_courses.map((c) => [c.code, c]));

  // Requirements that name their courses: show every course as done or not.
  if (rule === "all_courses" || rule === "course_list") {
    return (
      <ul className="mt-2 grid gap-1 sm:grid-cols-2">
        {courses.map((course) => {
          const done = applied.get(course.code);
          return (
            <CourseRow
              key={course.code}
              done={Boolean(done)}
              code={course.code}
              name={course.name}
              grade={done?.grade}
            />
          );
        })}
      </ul>
    );
  }

  // Requirements met by "N courses/credits from a set": show what counted,
  // then what's left.
  const remaining = remainingText(requirement);
  return (
    <div className="mt-2">
      <ul className="grid gap-1 sm:grid-cols-2">
        {progress.applied_courses.map((course) => (
          <CourseRow
            key={course.code}
            done
            code={course.code}
            name={course.name}
            grade={course.grade}
          />
        ))}
        {remaining && (
          <li className="flex items-center gap-2 text-sm text-slate-500">
            <span className="h-4 w-4 shrink-0 rounded-full border-2 border-slate-300" />
            {remaining}
          </li>
        )}
      </ul>
      {(filters.length > 0 || courses.length > 0) && eligible_courses.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
            {eligibleLabel(filters)} ({eligible_count} in the catalog)
          </summary>
          <p className="mt-1 leading-relaxed text-slate-600">
            {eligible_courses.map((c) => c.code).join(", ")}
            {eligible_count > eligible_courses.length &&
              `, and ${eligible_count - eligible_courses.length} more (search Courses to see all)`}
          </p>
        </details>
      )}
    </div>
  );
}

function CourseRow({
  done,
  code,
  name,
  grade,
}: {
  done: boolean;
  code: string;
  name: string;
  grade?: string | null;
}) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {done ? (
        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-bold text-white">
          ✓
        </span>
      ) : (
        <span className="h-4 w-4 shrink-0 rounded-full border-2 border-slate-300" />
      )}
      <span className={done ? "font-medium" : "font-medium text-slate-500"}>{code}</span>
      <span className="truncate text-slate-500" title={name}>
        {name}
      </span>
      {grade !== undefined && (
        <span className="ml-auto shrink-0 text-xs text-slate-400">{grade ?? "no grade"}</span>
      )}
    </li>
  );
}

function summary(requirement: Requirement): string {
  const { rule, progress, courses, min_courses, min_credits, min_grade } = requirement;
  if (!progress) return "";
  const grade = min_grade ? ` · ${min_grade} or better` : "";
  switch (rule) {
    case "all_courses":
      return `${progress.applied_courses.length} of ${courses.length} courses${grade}`;
    case "min_courses":
      return `${progress.applied_courses.length} of ${min_courses} ${plural(min_courses ?? 0, "course")}${grade}`;
    case "min_credits":
      return `${progress.credits_completed} of ${min_credits} credits${grade}`;
    case "course_list":
      return `${progress.applied_courses.length} of ${courses.length} listed courses taken`;
    case "not_tracked":
      return "Not tracked yet";
    default:
      return "";
  }
}

function remainingText(requirement: Requirement): string | null {
  const { progress } = requirement;
  if (!progress) return null;
  if (progress.credits_remaining) {
    return `${progress.credits_remaining} ${plural(progress.credits_remaining, "credit")} remaining`;
  }
  if (progress.courses_remaining) {
    return `${progress.courses_remaining} ${plural(progress.courses_remaining, "course")} remaining`;
  }
  return null;
}

function eligibleLabel(filters: CourseFilter[]): string {
  if (filters.length === 0) return "Courses that count";
  const parts = filters.map((f) => {
    if (f.gen_ed) return `Gen Ed ${f.gen_ed}`;
    const subject = f.subject ?? "Any subject";
    if (f.min_number && f.max_number) return `${subject} ${f.min_number}–${f.max_number}`;
    if (f.min_number) return `${subject} ${f.min_number}+`;
    return subject;
  });
  return `Courses that count: ${parts.join(" or ")}`;
}

function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`;
}
