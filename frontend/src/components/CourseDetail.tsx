import type { SelectedCourse } from "@/components/CourseBrowser";
import { formatCredits, type PrerequisiteGroup, type PrerequisiteTree } from "@/lib/api";

const PREREQUISITE_SOURCES: Record<string, string> = {
  curated: "Reviewed by hand against the catalog.",
  parsed: "Read from the catalog wording, which matched a known pattern exactly.",
  partial: "Course part read from the catalog; the wording also allows something that isn't a course.",
  unstructured: "",
  none: "",
};

const TIMING_LABELS: Record<PrerequisiteGroup["timing"], string | null> = {
  before: null,
  before_or_concurrent: "or take in the same semester",
  concurrent: "must take in the same semester",
};

type Props = {
  selected: SelectedCourse;
  completed: Set<string>; // the student's completed courses, for check marks
  onSelectCourse: (code: string) => void;
};

export default function CourseDetail({ selected, completed, onSelectCourse }: Props) {
  const { course, dependents, tree } = selected;
  const { groups, complete, prerequisite_text, corequisite_text } = course.prerequisites;
  const deep = tree.groups.some((g) => g.options.some((o) => o.groups.length > 0));

  return (
    <article>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-red-700">
            {course.code}
            {course.department_name && (
              <span className="ml-2 font-normal text-slate-500">{course.department_name}</span>
            )}
            {completed.has(course.code) && (
              <span className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
                ✓ Completed
              </span>
            )}
          </p>
          <h2 className="mt-1 text-2xl font-bold tracking-tight">{course.name}</h2>
        </div>
        <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-sm font-medium text-slate-700">
          {formatCredits(course)}
        </span>
      </div>

      {!course.in_current_catalog && (
        <p className="mt-3 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
          Not in the current catalog. Kept for students who completed it; not suggested in plans.
        </p>
      )}

      {course.gen_ed.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-slate-500">Gen Ed:</span>
          {course.gen_ed.map((tag) => (
            <span key={tag} className="rounded bg-sky-50 px-1.5 py-0.5 font-medium text-sky-800">
              {tag}
            </span>
          ))}
          {course.gen_ed.length > 1 && course.gen_ed_text?.includes(" or ") && (
            <span className="text-slate-500">(counts as one, not both)</span>
          )}
        </p>
      )}
      {course.gen_ed_conditional.map((g) => (
        <p key={g.tag} className="mt-1 text-xs text-slate-500">
          Also {g.tag} {g.condition}. Not counted yet: Finish Line can&apos;t check that condition.
        </p>
      ))}
      {course.gen_ed_status === "none_found" && (
        <p className="mt-3 text-xs text-slate-500">
          No Gen Ed listing found on Testudo for Fall 2025 to Fall 2026. It may still be approved in
          other terms; it isn&apos;t counted toward Gen Ed here.
        </p>
      )}

      {course.description && <p className="mt-4 leading-relaxed text-slate-700">{course.description}</p>}

      {(course.restriction_text || course.credit_only_granted_for) && (
        <div className="mt-4 space-y-1 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {course.restriction_text && (
            <p>
              <span className="font-medium">Restriction:</span> {course.restriction_text}
            </p>
          )}
          {course.credit_only_granted_for && (
            <p>
              <span className="font-medium">Credit only granted for:</span>{" "}
              {course.credit_only_granted_for}
            </p>
          )}
        </div>
      )}

      <Heading>Prerequisites</Heading>
      {groups.length === 0 && complete && <p className="mt-2 text-slate-700">None</p>}
      {groups.length > 0 && (
        <ul className="mt-3 space-y-2">
          {groups.map((group, i) => (
            <li key={i} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {group.options.length > 1 && <span className="text-sm text-slate-500">One of:</span>}
                {group.options.map((option) => (
                  <CourseChip
                    key={option.code}
                    code={option.code}
                    title={option.name}
                    done={completed.has(option.code)}
                    onSelect={onSelectCourse}
                  />
                ))}
              </div>
              <GroupNotes group={group} />
            </li>
          ))}
        </ul>
      )}

      {course.prerequisites.status === "unstructured" && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          These prerequisites couldn&apos;t be verified as a list of courses, so Finish Line
          doesn&apos;t check them. Read the official wording below.
        </p>
      )}
      {!complete && course.prerequisites.status !== "unstructured" && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Some requirements can&apos;t be listed as courses. See the official wording below.
        </p>
      )}
      {groups.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">{PREREQUISITE_SOURCES[course.prerequisites.status]}</p>
      )}

      {(prerequisite_text || corequisite_text) && (
        <div className="mt-4 space-y-1 text-sm text-slate-500">
          {prerequisite_text && (
            <p>
              <span className="font-medium">Official prerequisite:</span> {prerequisite_text}
            </p>
          )}
          {corequisite_text && (
            <p>
              <span className="font-medium">Official corequisite:</span> {corequisite_text}
            </p>
          )}
        </div>
      )}

      {deep && (
        <>
          <Heading>Full prerequisite chain</Heading>
          <p className="mt-1 text-xs text-slate-500">
            Every level below {course.code}. Each group needs one of its courses.
          </p>
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 p-4">
            <TreeGroups node={tree} completed={completed} onSelect={onSelectCourse} />
          </div>
        </>
      )}

      <CatalogDetails course={course} />

      <Heading>Unlocks</Heading>
      {dependents.length === 0 ? (
        <p className="mt-2 text-slate-700">No courses list {course.code} as a prerequisite.</p>
      ) : (
        <>
          <p className="mt-1 text-xs text-slate-500">
            Courses that list {course.code} as a prerequisite.
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {dependents.map((d) => (
              <li key={d.code} className="text-sm">
                <CourseChip
                  code={d.code}
                  title={d.name}
                  done={completed.has(d.code)}
                  onSelect={onSelectCourse}
                />
                {d.alternatives.length > 0 && (
                  <span className="ml-1 text-xs text-slate-500">
                    (or {d.alternatives.join(", ")})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}

function TreeGroups({
  node,
  completed,
  onSelect,
}: {
  node: PrerequisiteTree;
  completed: Set<string>;
  onSelect: (code: string) => void;
}) {
  if (node.groups.length === 0) return null;
  return (
    <ul className="space-y-2">
      {node.groups.map((group, i) => (
        <li key={i}>
          {group.options.length > 1 && <span className="text-xs text-slate-500">One of:</span>}
          <ul className="space-y-1.5">
            {group.options.map((option) => (
              <li key={option.code}>
                <span className="text-sm">
                  <CourseChip
                    code={option.code}
                    title={option.name}
                    done={completed.has(option.code)}
                    onSelect={onSelect}
                  />{" "}
                  <span className="text-slate-500">{option.name}</span>
                  {option.cycle && <span className="text-xs text-slate-400"> (circular)</span>}
                </span>
                {option.groups.length > 0 && !completed.has(option.code) && (
                  <div className="mt-1.5 ml-3 border-l-2 border-slate-200 pl-3">
                    <TreeGroups node={option} completed={completed} onSelect={onSelect} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function CourseChip({
  code,
  title,
  done,
  onSelect,
}: {
  code: string;
  title: string;
  done: boolean;
  onSelect: (code: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(code)}
      title={title}
      className={`rounded px-2 py-0.5 text-sm font-medium ring-1 hover:bg-red-50 ${
        done ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-white text-red-700 ring-slate-200"
      }`}
    >
      {done && <span aria-label="Completed">✓ </span>}
      {code}
    </button>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mt-8 text-sm font-semibold tracking-wider text-slate-500 uppercase">{children}</h3>
  );
}

function GroupNotes({ group }: { group: PrerequisiteGroup }) {
  const notes = [group.min_grade && `Minimum grade ${group.min_grade}`, TIMING_LABELS[group.timing]].filter(
    Boolean,
  );
  if (notes.length === 0) return null;
  return <p className="mt-1 text-xs text-slate-500">{notes.join(" · ")}</p>;
}

function CatalogDetails({ course }: { course: SelectedCourse["course"] }) {
  const rows: [string, string | null][] = [
    ["Formerly", course.formerly],
    ["Cross-listed with", course.cross_listed_with],
    ["Jointly offered with", course.jointly_offered_with],
    ["Repeatable to", course.repeatable_to],
    ["Recommended", course.recommended],
    ["Additional information", course.additional_information],
  ];
  const shown = rows.filter(([, value]) => value);
  return (
    <>
      {shown.length > 0 && (
        <dl className="mt-6 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
          {shown.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="font-medium text-slate-500">{label}</dt>
              <dd className="text-slate-700">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {course.source_url && (
        <p className="mt-4 text-xs text-slate-400">
          Source:{" "}
          <a href={course.source_url} className="underline hover:text-slate-600">
            UMD Undergraduate Catalog {course.catalog_year}
          </a>
          {course.gen_ed_term && <> · Gen Ed from Testudo ({termName(course.gen_ed_term)})</>}
        </p>
      )}
    </>
  );
}

function termName(term: string): string {
  const year = term.slice(0, 4);
  const season = { "01": "Spring", "05": "Summer", "08": "Fall", "12": "Winter" }[term.slice(4)];
  return season ? `${season} ${season === "Winter" ? Number(year) + 1 : year}` : term;
}
