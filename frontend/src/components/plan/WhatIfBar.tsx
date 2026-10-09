"use client";

import { useState } from "react";
import type { GraduationPlan } from "@/lib/api";

type Props = {
  plan: GraduationPlan;
  terms: string[];
  busy: boolean;
  onTry: (code: string, term: string) => void;
};

// "What if I take INST326 in Spring 2027 instead?"
export default function WhatIfBar({ plan, terms, busy, onTry }: Props) {
  const courses = plan.terms.flatMap((t) =>
    t.courses.filter((c) => c.code).map((c) => ({ code: c.code as string, term: t.term })),
  );
  const [code, setCode] = useState("");
  const [term, setTerm] = useState("");

  const current = courses.find((c) => c.code === code)?.term;
  const canTry = code && term && term !== current && !busy;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <form
        className="flex flex-wrap items-center gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (canTry) onTry(code, term);
        }}
      >
        <span className="font-medium text-slate-700">What if I take</span>
        <select
          aria-label="Course"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5"
        >
          <option value="">a course…</option>
          {courses.map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} (now {c.term})
            </option>
          ))}
        </select>
        <span className="font-medium text-slate-700">in</span>
        <select
          aria-label="Semester"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5"
        >
          <option value="">a semester…</option>
          {terms.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <span className="font-medium text-slate-700">instead?</span>
        <button
          type="submit"
          disabled={!canTry}
          className="rounded-lg bg-slate-900 px-3 py-1.5 font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Try it
        </button>
      </form>
      <p className="mt-2 text-xs text-slate-500">
        Everything that depends on it is re-planned. Nothing is saved until you choose Save changes.
      </p>
    </section>
  );
}
