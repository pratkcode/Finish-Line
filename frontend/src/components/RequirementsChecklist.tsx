"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import RequirementItem from "@/components/RequirementItem";
import StatusIcon, { STATUS_LABELS } from "@/components/StatusIcon";
import UnverifiedMajorNote from "@/components/UnverifiedMajorNote";
import { ErrorState, LoadingState } from "@/components/ui/States";
import {
  ApiError,
  getPrograms,
  getProgress,
  getSession,
  type ProgressResponse,
  type RequirementStatus,
} from "@/lib/api";
import { readSessionId } from "@/lib/session";

const CATEGORY_LABELS: Record<string, string> = {
  major: "Major requirements",
  university: "University requirements",
  general_education: "University requirements",
};

type Loaded = { data: ProgressResponse; hasProfile: boolean };

// The student's courses when they have a profile; otherwise the requirements
// with nothing completed, for the first program the API offers.
async function loadRequirements(): Promise<Loaded> {
  const id = readSessionId();
  if (id) {
    try {
      const session = await getSession(id);
      const courses = session.courses.map(({ code, grade, credits }) => ({ code, grade, credits }));
      return { data: await getProgress(session.program_slug, courses), hasProfile: true };
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) throw err;
    }
  }
  const [program] = await getPrograms();
  if (!program) throw new Error("No programs are set up yet.");
  return { data: await getProgress(program.slug, []), hasProfile: false };
}

type State = { status: "loading" } | { status: "error"; message: string } | ({ status: "ready" } & Loaded);

export default function RequirementsChecklist() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async () => {
    try {
      setState({ status: "ready", ...(await loadRequirements()) });
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }, []);

  useEffect(() => {
    queueMicrotask(load);
  }, [load]);

  if (state.status === "loading") return <LoadingState label="Loading requirements" />;
  if (state.status === "error") {
    return (
      <ErrorState
        message={state.message}
        onRetry={() => {
          setState({ status: "loading" });
          load();
        }}
      />
    );
  }

  const { data, hasProfile } = state;
  return (
    <div className="space-y-6">
      {!hasProfile && (
        <p className="rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-700">
          Showing the requirements with no courses completed.{" "}
          <Link href="/profile" className="font-medium text-red-700 hover:underline">
            Add your courses
          </Link>{" "}
          to check them off.
        </p>
      )}

      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-lg font-semibold">
          {data.program.name}{" "}
          <span className="font-normal text-slate-500">· {data.program.university}</span>
        </p>
        <Legend />
      </div>

      {data.program.requirements_status !== "verified" && <UnverifiedMajorNote program={data.program} />}

      {data.unrecognized_courses.length > 0 && (
        <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700">
          Not in the course database yet, so not counted: {data.unrecognized_courses.join(", ")}
        </p>
      )}

      {data.requirements.map((requirement) => (
        <section key={requirement.key} className="rounded-xl border border-slate-200 bg-white p-6">
          <p className="mb-3 text-xs font-semibold tracking-wider text-slate-400 uppercase">
            {CATEGORY_LABELS[requirement.category] ?? requirement.category}
          </p>
          <ul>
            <RequirementItem requirement={requirement} />
          </ul>
          {requirement.source_url && (
            <p className="mt-4 text-xs text-slate-400">
              Source:{" "}
              <a href={requirement.source_url} className="underline hover:text-slate-600">
                {new URL(requirement.source_url).hostname}
              </a>
            </p>
          )}
        </section>
      ))}
    </div>
  );
}

function Legend() {
  const statuses: RequirementStatus[] = ["complete", "in_progress", "not_started", "not_tracked"];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-slate-600">
      {statuses.map((status) => (
        <li key={status} className="flex items-center gap-1.5">
          <StatusIcon status={status} />
          {STATUS_LABELS[status]}
        </li>
      ))}
    </ul>
  );
}
