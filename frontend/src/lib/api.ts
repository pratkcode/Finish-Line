export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Every request goes through here: JSON in and out, and a typed error with the
// API's message (FastAPI's {"detail": ...}) when something fails.
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  options: { body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Can't reach the Finish Line server. Is the backend running?");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = typeof data?.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const get = <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, { signal });
const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(method, path, { body });

export type HealthResponse = {
  status: string;
  database: string;
};

export type CourseSummary = {
  code: string;
  name: string;
  credits_min: number;
  credits_max: number;
};

export type PrerequisiteGroup = {
  timing: "before" | "before_or_concurrent" | "concurrent";
  min_grade: string | null;
  // Any one of these satisfies the group.
  options: CourseSummary[];
};

export type Prerequisites = {
  course_code: string;
  // Every group must be satisfied.
  groups: PrerequisiteGroup[];
  // False when the official text has conditions the groups don't capture.
  complete: boolean;
  prerequisite_text: string | null;
  corequisite_text: string | null;
};

export type CourseDetail = CourseSummary & CourseDetailExtras & {
  description: string | null;
  prerequisites: Prerequisites;
};

export function getHealth(): Promise<HealthResponse> {
  return get("/api/health");
}

export function getCourses(
  search: string,
  signal?: AbortSignal,
): Promise<CourseSummary[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return get(`/api/courses${query}`, signal);
}

export function getCourse(
  code: string,
  signal?: AbortSignal,
): Promise<CourseDetail> {
  return get(`/api/courses/${encodeURIComponent(code)}`, signal);
}

export function formatCredits(course: CourseSummary): string {
  const { credits_min: min, credits_max: max } = course;
  const range = min === max ? `${min}` : `${min}–${max}`;
  return `${range} ${max === 1 ? "credit" : "credits"}`;
}

export type Program = {
  slug: string;
  name: string;
  university: string;
};

export type RequirementStatus =
  | "complete"
  | "in_progress"
  | "not_started"
  | "not_tracked";

export type RequirementRule =
  | "all_courses"
  | "min_courses"
  | "min_credits"
  | "all_children"
  | "any_child"
  | "course_list"
  | "not_tracked";

export type CourseFilter = {
  subject: string | null;
  min_number: number | null;
  max_number: number | null;
  gen_ed: string | null;
};

export type AppliedCourse = {
  code: string;
  name: string;
  credits: number;
  grade: string | null; // null = not entered
};

export type RequirementProgress = {
  status: RequirementStatus;
  applied_courses: AppliedCourse[];
  credits_completed: number;
  courses_remaining: number | null;
  credits_remaining: number | null;
};

export type Requirement = {
  key: string;
  name: string;
  description: string | null;
  category: string;
  rule: RequirementRule;
  optional: boolean;
  min_courses: number | null;
  min_credits: number | null;
  min_grade: string | null;
  source_url: string | null;
  courses: CourseSummary[];
  filters: CourseFilter[];
  eligible_courses: CourseSummary[];
  progress: RequirementProgress | null;
  children: Requirement[];
};

export type TakenCourse = {
  code: string;
  grade?: string | null;
  credits?: number;
};

export type ProgressResponse = {
  program: Program;
  requirements: Requirement[];
  unrecognized_courses: string[];
};

export function getProgress(programSlug: string, courses: TakenCourse[]): Promise<ProgressResponse> {
  return send("POST", `/api/programs/${encodeURIComponent(programSlug)}/progress`, { courses });
}

export function getPrograms(signal?: AbortSignal): Promise<Program[]> {
  return get("/api/programs", signal);
}

export type CompletedCourse = {
  code: string;
  name: string;
  credits: number;
  credits_min: number;
  credits_max: number;
  grade: string | null;
};

export type PlanSession = {
  id: string;
  program_slug: string;
  program_name: string;
  university: string;
  current_term: string | null;
  max_credits_per_term: number;
  courses: CompletedCourse[];
  credits: {
    // Calculated from the course list; the number to use.
    completed: number;
    // What the student typed in, if anything.
    reported: number | null;
    // Reported credits not backed by a listed course.
    unmatched: number;
    reported_too_low: boolean;
  };
};

export type SessionChanges = Partial<{
  program_slug: string;
  reported_credits: number | null;
  current_term: string | null;
  max_credits_per_term: number;
}>;

export function createSession(changes: SessionChanges & { program_slug: string }) {
  return send<PlanSession>("POST", "/api/sessions", changes);
}

export function getSession(id: string) {
  return get<PlanSession>(`/api/sessions/${id}`);
}

export function updateSession(id: string, changes: SessionChanges) {
  return send<PlanSession>("PATCH", `/api/sessions/${id}`, changes);
}

export function deleteSession(id: string) {
  return send<void>("DELETE", `/api/sessions/${id}`);
}

export function addCompletedCourse(id: string, code: string) {
  return send<PlanSession>("POST", `/api/sessions/${id}/courses`, { code });
}

export function updateCompletedCourse(
  id: string,
  code: string,
  changes: { grade?: string | null; credits?: number },
) {
  return send<PlanSession>("PATCH", `/api/sessions/${id}/courses/${code}`, changes);
}

export function removeCompletedCourse(id: string, code: string) {
  return send<PlanSession>("DELETE", `/api/sessions/${id}/courses/${code}`);
}

export type CandidateCourse = CourseSummary & {
  // Set when the student took it but the grade was too low to count.
  earned_grade: string | null;
};

export type RequirementSummary = {
  key: string;
  name: string;
  path: string[];
  category: string;
  rule: RequirementRule;
  status: RequirementStatus;
  min_grade: string | null;
  courses_remaining: number | null;
  credits_remaining: number | null;
  applied_courses: AppliedCourse[];
  candidate_courses: CandidateCourse[];
  options: string[];
};

export type DegreeProgress = {
  session_id: string;
  program: Program;
  credits: {
    from_courses: number;
    unverified: number;
    counted: number;
    required: number | null;
    remaining: number | null;
  };
  completed_requirements: RequirementSummary[];
  remaining_requirements: RequirementSummary[];
  untracked_requirements: RequirementSummary[];
  requirements: Requirement[];
};

export function getDegreeProgress(sessionId: string) {
  return get<DegreeProgress>(`/api/sessions/${sessionId}/progress`);
}

export type CourseRef = CourseSummary;

export type EligibilityStatus =
  | "completed"
  | "available"
  | "available_with_concurrent"
  | "blocked";

export type PrerequisiteOptionState = CourseRef & {
  state: "completed" | "low_grade" | "available" | "blocked";
  grade: string | null;
};

export type PrerequisiteGroupState = {
  timing: "before" | "before_or_concurrent" | "concurrent";
  min_grade: string | null;
  state: "met" | "concurrent" | "missing";
  options: PrerequisiteOptionState[]; // any one satisfies the group
};

export type CourseEligibility = CourseRef & {
  status: EligibilityStatus;
  groups: PrerequisiteGroupState[]; // every group must be met
  complete_first: CourseRef[];
  take_with: CourseRef[];
  additional_conditions: string | null;
  retake: boolean;
  satisfies: { key: string; name: string }[];
};

export type EligibilityAnalysis = {
  session_id: string;
  current_term: string | null;
  available: CourseEligibility[];
  blocked: CourseEligibility[];
  missing_prerequisites: (CourseRef & { status: EligibilityStatus; unlocks: string[] })[];
};

export function getEligibility(sessionId: string) {
  return get<EligibilityAnalysis>(`/api/sessions/${sessionId}/eligibility`);
}

export type PlannedCourse = {
  code: string | null; // null for "choose a course" slots and general electives
  name: string;
  credits: number;
  kind: "course" | "placeholder" | "elective";
  required: boolean;
  retake: boolean;
  satisfies: { key: string | null; name: string; category: string | null }[];
  prerequisites: string[];
  notes: string[];
  pinned: boolean; // placed by the student
  warnings: string[]; // rules this placement breaks
};

export type PlannedTerm = {
  term: string;
  credits: number;
  warnings: string[];
  courses: PlannedCourse[];
};

export type Placement = { code: string; term: string };

export type PlanOverrides = {
  pinned: Placement[]; // courses the student placed in a semester
  removed: string[]; // courses the student took out
};

export type GraduationPlan = {
  disclaimer: string;
  start_term: string;
  max_credits_per_term: number;
  projected_graduation: string | null;
  graduation_note: string;
  warnings: { term: string; code: string | null; message: string }[];
  pinned: Placement[];
  removed: string[];
  credits: {
    remaining: number;
    completed: number;
    planned: number;
    total: number;
    required: number | null;
  };
  terms: PlannedTerm[];
  unscheduled: (PlannedCourse & { reason: string })[];
  unplanned_requirements: { key: string; name: string; reason: string }[];
  not_checked: { key: string; name: string }[];
  assumptions: string[];
};

export type PlanPreview = GraduationPlan & {
  changes: {
    graduation_before: string | null;
    graduation_after: string | null;
    moved: { code: string; name: string; from_term: string | null; to_term: string | null }[];
  };
};

export function getGraduationPlan(sessionId: string) {
  return get<GraduationPlan>(`/api/sessions/${sessionId}/plan`);
}

export function previewPlan(sessionId: string, overrides: PlanOverrides) {
  return send<PlanPreview>("POST", `/api/sessions/${sessionId}/plan/preview`, overrides);
}

export function savePlanOverrides(sessionId: string, overrides: PlanOverrides) {
  return send<GraduationPlan>("PUT", `/api/sessions/${sessionId}/plan/overrides`, overrides);
}

export type CourseDetailExtras = {
  gen_ed: string[];
  gen_ed_text: string | null;
  restriction_text: string | null;
  credit_only_granted_for: string | null;
};

export type Dependent = CourseSummary & {
  timing: "before" | "before_or_concurrent" | "concurrent";
  min_grade: string | null;
  alternatives: string[]; // other courses that satisfy the same prerequisite
};

export function getDependents(code: string, signal?: AbortSignal) {
  return get<Dependent[]>(`/api/courses/${encodeURIComponent(code)}/dependents`, signal);
}

export type PrerequisiteTree = CourseSummary & {
  prerequisites_complete: boolean;
  cycle: boolean;
  groups: {
    timing: "before" | "before_or_concurrent" | "concurrent";
    min_grade: string | null;
    options: PrerequisiteTree[];
  }[];
};

export function getPrerequisiteTree(code: string, signal?: AbortSignal) {
  return get<PrerequisiteTree>(`/api/courses/${encodeURIComponent(code)}/prerequisite-tree`, signal);
}

export type DashboardSummary = {
  session_id: string;
  program: Program;
  current_term: string | null;
  max_credits_per_term: number;
  completed_courses: number;
  credits: {
    earned: number;
    from_courses: number;
    unverified: number;
    required: number | null;
    remaining: number | null;
  };
  requirements: { complete: number; remaining: number; not_tracked: number; percent: number };
  graduation: { projected: string | null; semesters: number; warnings: number; has_changes: boolean };
  next_term: { term: string; credits: number; courses: string[] } | null;
  eligibility: { available: number; blocked: number };
  top_prerequisite: CourseSummary | null;
};

export function getDashboard(sessionId: string) {
  return get<DashboardSummary>(`/api/sessions/${sessionId}/summary`);
}

export const GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P"];
