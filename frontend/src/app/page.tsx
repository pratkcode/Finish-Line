import Link from "next/link";
import { Logo } from "@/components/SiteHeader";

const FEATURES = [
  {
    title: "Degree requirements",
    body: "Every UMD Information Science, Gen Ed, and university requirement, checked against your courses.",
  },
  {
    title: "Prerequisites",
    body: "See what each course requires and unlocks, and what you can take right now.",
  },
  {
    title: "Graduation plan",
    body: "A semester-by-semester path to your earliest graduation, which you can rearrange with what-ifs.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <Link href="/dashboard" className="text-sm font-medium text-slate-600 hover:text-slate-900">
          Open dashboard →
        </Link>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center px-4 py-16 sm:px-6">
        <p className="text-sm font-semibold tracking-wider text-red-700 uppercase">
          UMD Information Science
        </p>
        <h1 className="mt-3 max-w-2xl text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
          Your degree. Your plan. Your finish line.
        </h1>
        <p className="mt-5 max-w-xl text-lg text-slate-600">
          Enter the courses you&apos;ve completed. Finish Line shows what&apos;s left, what you can
          take next, and the earliest semester you could graduate.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/profile"
            className="rounded-lg bg-red-700 px-5 py-2.5 font-medium text-white hover:bg-red-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2"
          >
            Start Planning
          </Link>
          <Link
            href="/courses"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-50"
          >
            Browse courses
          </Link>
        </div>

        <ul className="mt-16 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <li key={f.title} className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="font-semibold text-slate-900">{f.title}</p>
              <p className="mt-1 text-sm text-slate-600">{f.body}</p>
            </li>
          ))}
        </ul>
      </main>

      <footer className="mx-auto w-full max-w-5xl px-4 py-6 text-sm text-slate-500 sm:px-6">
        Finish Line is a planning tool, not an official UMD degree audit. Confirm plans with your
        advisor.
      </footer>
    </div>
  );
}
