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
  // Where the groups come from. "unstructured": only the official wording is known.
  status: "curated" | "parsed" | "partial" | "unstructured" | "none";
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

export type CourseSearchResult = {
  courses: CourseSummary[];
  total: number; // all matches; `courses` is capped (see the API's X-Total-Count)
};

export async function searchCourses(
  search: string,
  options: { department?: string; limit?: number; signal?: AbortSignal } = {},
): Promise<CourseSearchResult> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (options.department) params.set("department", options.department);
  if (options.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API_URL}/api/courses${query}`, { signal: options.signal }).catch((err) => {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Can't reach the Finish Line server. Is the backend running?");
  });
  if (!res.ok) throw new ApiError(res.status, `Search failed (${res.status})`);
  const courses: CourseSummary[] = await res.json();
  return { courses, total: Number(res.headers.get("X-Total-Count") ?? courses.length) };
}

export async function getCourses(search: string, signal?: AbortSignal): Promise<CourseSummary[]> {
  return (await searchCourses(search, { signal })).courses;
}

export type Department = { code: string; name: string; course_count: number };

export function getDepartments(signal?: AbortSignal) {
  return get<Department[]>("/api/courses/departments", signal);
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
  // "verified": Finish Line has this major's requirements from the UMD catalog.
  // "not_available": the major exists, but its requirements aren't in Finish Line yet.
  requirements_status: "verified" | "not_available";
  catalog_url: string | null;
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
  eligible_courses: CourseSummary[]; // capped; see eligible_count
  eligible_count: number;
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
  status: CourseStatus;
  academic_term_id: number | null; // the UMD semester it was taken in, if recorded
};

export type CourseStatus = "completed" | "in_progress";

export type PlanSession = {
  id: string;
  program_slug: string;
  program_name: string;
  university: string;
  current_term: string | null;
  max_credits_per_term: number;
  plan_start_term: string | null; // null: the semester after current_term
  target_graduation_term: string | null;
  academic_standing: string | null;
  include_summer: boolean;
  max_summer_credits: number | null;
  courses: CompletedCourse[];
  credits: {
    // Calculated from the course list; the number to use.
    completed: number;
    in_progress: number;
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
  plan_start_term: string | null;
  target_graduation_term: string | null;
  academic_standing: string | null;
  include_summer: boolean;
  max_summer_credits: number | null;
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

export function addCompletedCourse(
  id: string,
  code: string,
  extra: { status?: CourseStatus; academic_term_id?: number | null; grade?: string | null } = {},
) {
  return send<PlanSession>("POST", `/api/sessions/${id}/courses`, { code, ...extra });
}

export function updateCompletedCourse(
  id: string,
  code: string,
  changes: { grade?: string | null; credits?: number; status?: CourseStatus; academic_term_id?: number | null },
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
  candidate_courses: CandidateCourse[]; // capped; see candidate_count
  candidate_count: number;
  options: string[];
  fulfilled: boolean; // met by a verified fulfillment (transfer evaluation, waiver, ...)
  in_progress_courses: string[]; // courses being taken now that would count here
};

export type PendingItem = { kind: string; description: string; credits: number; reason: string };

export type DegreeProgress = {
  session_id: string;
  program: Program;
  credits: {
    earned: number; // all completed credit recorded, verified or not
    applicable: number; // what counts toward the degree
    from_courses: number;
    credit_block: number; // verified transfer credit without a UMD equivalent
    unverified: number; // recorded or reported but not counted until verified
    in_progress: number;
    required: number | null;
    remaining: number | null;
  };
  pending: PendingItem[];
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

// --- The student's saved semester plan -------------------------------------------

export type RequirementRef = { key: string | null; name: string; category: string | null };

export type PlannedCourse = {
  code: string;
  name: string;
  credits: number; // credits this course counts for in the plan
  credits_min: number;
  credits_max: number;
  retake: boolean; // completed before with too low a grade; adds no new credits
  satisfies: RequirementRef[];
  prerequisites: string[]; // planned courses this depends on
  notes: string[];
  warnings: string[]; // rules this placement breaks
};

export type PlannedTerm = {
  term: string;
  credits: number; // sum of this semester's courses
  limit: number; // credit limit for this semester
  warnings: string[];
  courses: PlannedCourse[];
};

export type StudentPlan = {
  program_name: string;
  requirements_verified: boolean;
  current_term: string;
  plan_start_term: string; // first semester of the future plan
  include_summer: boolean;
  max_credits_per_term: number;
  max_summer_credits: number | null;
  target_graduation_term: string | null;
  history: HistoryTerm[]; // past and current semesters
  planning_terms: string[]; // future semesters to show
  projected_graduation: string | null;
  graduation_note: string;
  target: TargetCheck | null;
  credits: {
    completed: number;
    in_progress: number;
    planned: number;
    total: number;
    required: number | null;
    remaining: number | null;
    unverified: number;
  };
  terms: PlannedTerm[];
  warnings: { term: string; code: string | null; message: string }[];
  still_needed: {
    key: string;
    name: string;
    path: string[];
    courses_remaining: number | null;
    credits_remaining: number | null;
  }[];
  not_checked: { key: string; name: string }[];
};

export type RecommendedCourse = {
  code: string | null; // null for a slot where you choose the course
  name: string;
  credits: number;
  term: string;
  satisfies: RequirementRef[];
  reasons: string[]; // why it's recommended
  uncertain: string[]; // what couldn't be verified
};

export type TargetCheck = { term: string; meets: boolean | null; message: string };

export type Recommendation = {
  disclaimer: string;
  start_term: string;
  projected_graduation: string | null;
  graduation_note: string;
  target: TargetCheck | null;
  additions: RecommendedCourse[];
  slots: RecommendedCourse[];
  unscheduled: string[];
  assumptions: string[];
};

const planPath = (sessionId: string, rest = "") => `/api/sessions/${sessionId}/plan${rest}`;

export function getPlan(sessionId: string) {
  return get<StudentPlan>(planPath(sessionId));
}

export function addPlannedCourse(sessionId: string, code: string, term: string, credits?: number) {
  return send<StudentPlan>("POST", planPath(sessionId, "/courses"), { code, term, credits });
}

export function updatePlannedCourse(
  sessionId: string,
  code: string,
  changes: { term?: string; credits?: number },
) {
  return send<StudentPlan>("PATCH", planPath(sessionId, `/courses/${code}`), changes);
}

export function removePlannedCourse(sessionId: string, code: string) {
  return send<StudentPlan>("DELETE", planPath(sessionId, `/courses/${code}`));
}

export function clearPlan(sessionId: string) {
  return send<StudentPlan>("DELETE", planPath(sessionId));
}

export function getRecommendation(sessionId: string) {
  return send<Recommendation>("POST", planPath(sessionId, "/recommendation"));
}

export function acceptRecommendation(sessionId: string, courses: { code: string; term: string }[]) {
  return send<StudentPlan>("POST", planPath(sessionId, "/recommendation/accept"), { courses });
}

export type CourseDetailExtras = {
  department: string;
  department_name: string | null;
  catalog_year: string | null;
  source_url: string | null;
  in_current_catalog: boolean;
  gen_ed: string[]; // verified tags that count toward requirements
  gen_ed_conditional: { tag: string; condition: string }[]; // shown, not counted
  gen_ed_text: string | null;
  gen_ed_status: "verified" | "none_found";
  gen_ed_term: string | null;
  prerequisite_status: Prerequisites["status"];
  restriction_text: string | null;
  credit_only_granted_for: string | null;
  formerly: string | null;
  cross_listed_with: string | null;
  jointly_offered_with: string | null;
  repeatable_to: string | null;
  recommended: string | null;
  additional_information: string | null;
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
  plan_start_term: string;
  max_credits_per_term: number;
  completed_courses: number;
  in_progress_courses: number;
  credits: {
    earned: number; // counts toward the degree
    from_courses: number;
    in_progress: number;
    unverified: number;
    required: number | null;
    remaining: number | null;
  };
  requirements: { complete: number; remaining: number; not_tracked: number; percent: number };
  graduation: {
    projected: string | null; // from the saved plan
    note: string;
    semesters: number;
    planned_courses: number;
    warnings: number;
  };
  next_term: { term: string; credits: number; courses: string[] } | null;
  eligibility: { available: number; blocked: number };
  top_prerequisite: CourseSummary | null;
};

export function getDashboard(sessionId: string) {
  return get<DashboardSummary>(`/api/sessions/${sessionId}/summary`);
}

export const GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P"];

// --- Academic history -------------------------------------------------------------

export type HistoryCourse = {
  code: string;
  name: string;
  credits: number;
  credits_min: number;
  credits_max: number;
  grade: string | null;
  status: CourseStatus;
};

export type TransferVerification = "student_reported" | "umd_verified";
export type FulfillmentVerification = "student_reported" | "umd_verified" | "approved_exception";
export type FulfillmentMethod =
  | "transfer_credit"
  | "exam_credit"
  | "waiver"
  | "substitution"
  | "associate_degree"
  | "other";

export type TransferCredit = {
  id: number;
  academic_term_id: number | null;
  institution: string;
  kind: "course" | "credits"; // "credits": doesn't map to one course
  external_code: string | null;
  title: string | null;
  credits: number;
  grade: string | null;
  status: CourseStatus;
  equivalent_code: string | null;
  equivalent_name: string | null;
  verification: TransferVerification;
  verification_note: string | null;
  counted: boolean;
};

export type HistoryTerm = {
  id: number;
  term: string;
  institution: string;
  at_umd: boolean;
  period: "past" | "current" | "future";
  courses: HistoryCourse[];
  transfers: TransferCredit[];
};

export type Fulfillment = {
  id: number;
  requirement_key: string;
  requirement_name: string;
  method: FulfillmentMethod;
  verification: FulfillmentVerification;
  note: string | null;
  transfer_credit_id: number | null;
  counted: boolean;
};

export type AcademicHistory = {
  current_term: string;
  terms: HistoryTerm[];
  unassigned_courses: HistoryCourse[];
  unassigned_transfers: TransferCredit[];
  fulfillments: Fulfillment[];
  requirement_options: { key: string; name: string; path: string[]; category: string }[];
  summary: {
    earned_credits: number;
    applicable_credits: number;
    in_progress_credits: number;
    pending: PendingItem[];
  };
};

export type TransferInput = {
  academic_term_id?: number | null;
  institution?: string | null;
  kind?: "course" | "credits";
  external_code?: string | null;
  title?: string | null;
  credits?: number;
  grade?: string | null;
  status?: CourseStatus;
  equivalent_code?: string | null;
  verification?: TransferVerification;
  verification_note?: string | null;
};

const historyPath = (sessionId: string, rest = "") => `/api/sessions/${sessionId}${rest}`;

export function getHistory(sessionId: string) {
  return get<AcademicHistory>(historyPath(sessionId, "/history"));
}

export function addHistoryTerm(sessionId: string, term: { term: string; institution?: string | null; at_umd: boolean }) {
  return send<AcademicHistory>("POST", historyPath(sessionId, "/history/terms"), term);
}

export function updateHistoryTerm(sessionId: string, id: number, changes: { term?: string; institution?: string }) {
  return send<AcademicHistory>("PATCH", historyPath(sessionId, `/history/terms/${id}`), changes);
}

export function removeHistoryTerm(sessionId: string, id: number) {
  return send<AcademicHistory>("DELETE", historyPath(sessionId, `/history/terms/${id}`));
}

export function addTransfer(sessionId: string, transfer: TransferInput) {
  return send<AcademicHistory>("POST", historyPath(sessionId, "/transfer-credits"), transfer);
}

export function updateTransfer(sessionId: string, id: number, changes: TransferInput) {
  return send<AcademicHistory>("PATCH", historyPath(sessionId, `/transfer-credits/${id}`), changes);
}

export function removeTransfer(sessionId: string, id: number) {
  return send<AcademicHistory>("DELETE", historyPath(sessionId, `/transfer-credits/${id}`));
}

export function addFulfillment(
  sessionId: string,
  fulfillment: { requirement_key: string; method: FulfillmentMethod; verification: FulfillmentVerification; note?: string | null },
) {
  return send<AcademicHistory>("POST", historyPath(sessionId, "/fulfillments"), fulfillment);
}

export function updateFulfillment(
  sessionId: string,
  id: number,
  changes: { method?: FulfillmentMethod; verification?: FulfillmentVerification; note?: string | null },
) {
  return send<AcademicHistory>("PATCH", historyPath(sessionId, `/fulfillments/${id}`), changes);
}

export function removeFulfillment(sessionId: string, id: number) {
  return send<AcademicHistory>("DELETE", historyPath(sessionId, `/fulfillments/${id}`));
}

// --- Terms ------------------------------------------------------------------------

export const SEASONS = ["Winter", "Spring", "Summer", "Fall"] as const;

export function termOrder(term: string): number {
  const [season, year] = term.split(" ");
  return Number(year) * 4 + SEASONS.indexOf(season as (typeof SEASONS)[number]);
}

export function nextTerm(term: string, seasons: readonly string[] = ["Spring", "Fall"]): string {
  let value = termOrder(term) + 1;
  while (!seasons.includes(SEASONS[value % 4])) value += 1;
  return `${SEASONS[value % 4]} ${Math.floor(value / 4)}`;
}

/** Terms from `first` to `last`, inclusive, using the given seasons. */
export function termRange(first: string, last: string, seasons: readonly string[]): string[] {
  const out: string[] = [];
  for (let t = first; termOrder(t) <= termOrder(last) && out.length < 60; t = nextTerm(t, seasons)) out.push(t);
  return out;
}
