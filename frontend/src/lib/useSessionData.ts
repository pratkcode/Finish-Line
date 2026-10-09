"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { readSessionId } from "@/lib/session";

export type SessionData<T> =
  | { status: "loading" }
  | { status: "no-plan" } // no saved session in this browser (or it was deleted)
  | { status: "error"; message: string }
  | { status: "ready"; sessionId: string; data: T };

// Loads something that belongs to the student's saved planning session.
export function useSessionData<T>(load: (sessionId: string) => Promise<T>) {
  const [state, setState] = useState<SessionData<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = readSessionId();
    const run = async (): Promise<SessionData<T>> => {
      if (!id) return { status: "no-plan" };
      try {
        return { status: "ready", sessionId: id, data: await load(id) };
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return { status: "no-plan" };
        return { status: "error", message: err instanceof Error ? err.message : "Something went wrong." };
      }
    };
    run().then((next) => !cancelled && setState(next));
    return () => {
      cancelled = true;
    };
    // `load` is expected to be a stable module-level function.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { state, setState, retry };
}
