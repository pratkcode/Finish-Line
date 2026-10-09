import Link from "next/link";

// Placeholder blocks shaped like the content that's loading.
export function LoadingState({ label = "Loading…", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-4">
      <span className="sr-only">{label}</span>
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 rounded-xl border border-slate-200 bg-white p-5">
            <div className="h-3 w-24 rounded bg-slate-100" />
            <div className="mt-3 h-6 w-32 rounded bg-slate-100" />
          </div>
        ))}
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-28 rounded-xl border border-slate-200 bg-white p-5">
          <div className="h-4 w-40 rounded bg-slate-100" />
          <div className="mt-4 h-3 w-full rounded bg-slate-100" />
          <div className="mt-2 h-3 w-2/3 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6">
      <p className="font-semibold text-red-900">Something went wrong</p>
      <p className="mt-1 text-sm text-red-800">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  action?: { href: string; label: string };
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="text-lg font-semibold text-slate-900">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-slate-600">{children}</div>}
      {action && (
        <Link
          href={action.href}
          className="mt-5 inline-block rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}

// Shown on pages that need a planning session when there isn't one yet.
export function NoPlanState() {
  return (
    <EmptyState
      title="Set up your profile to get started"
      action={{ href: "/profile", label: "Set up your profile" }}
    >
      Add your major, current semester, and the courses you&apos;ve completed. Finish Line uses
      them to track requirements and build your graduation plan.
    </EmptyState>
  );
}
