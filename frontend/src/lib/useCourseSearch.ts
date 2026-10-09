"use client";

import { useEffect, useState } from "react";
import { getCourses, type CourseSummary } from "@/lib/api";

type Search = {
  results: CourseSummary[] | null; // null until the first response
  error: string | null;
};

// Course search against the API, waiting briefly after each keystroke.
// With allWhenEmpty, an empty query returns every course; otherwise nothing.
export function useCourseSearch(query: string, { allWhenEmpty = false, limit = 0 } = {}): Search {
  const [state, setState] = useState<Search>({ results: null, error: null });

  useEffect(() => {
    const q = query.trim();
    const controller = new AbortController();
    const timer = setTimeout(() => {
      if (!q && !allWhenEmpty) {
        setState({ results: [], error: null });
        return;
      }
      getCourses(q, controller.signal)
        .then((data) => setState({ results: limit ? data.slice(0, limit) : data, error: null }))
        .catch((err) => {
          if (!controller.signal.aborted) setState({ results: null, error: err.message });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, allWhenEmpty, limit]);

  return state;
}
