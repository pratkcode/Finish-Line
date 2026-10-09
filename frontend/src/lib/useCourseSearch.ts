"use client";

import { useEffect, useState } from "react";
import { searchCourses, type CourseSummary } from "@/lib/api";

type Search = {
  results: CourseSummary[] | null; // null until the first response
  total: number; // all matches (results may be capped)
  error: string | null;
};

// Course search against the API, waiting briefly after each keystroke.
// With allWhenEmpty, an empty query lists courses; otherwise it returns nothing.
export function useCourseSearch(
  query: string,
  { allWhenEmpty = false, limit = 0, department = "" } = {},
): Search {
  const [state, setState] = useState<Search>({ results: null, total: 0, error: null });

  useEffect(() => {
    const q = query.trim();
    const controller = new AbortController();
    const timer = setTimeout(() => {
      if (!q && !allWhenEmpty && !department) {
        setState({ results: [], total: 0, error: null });
        return;
      }
      searchCourses(q, { department, limit: limit || undefined, signal: controller.signal })
        .then(({ courses, total }) => setState({ results: courses, total, error: null }))
        .catch((err) => {
          if (!controller.signal.aborted) setState({ results: null, total: 0, error: err.message });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, allWhenEmpty, limit, department]);

  return state;
}
