import type { Program } from "@/lib/api";

// Shown wherever a page depends on major requirements that Finish Line doesn't have yet.
export default function UnverifiedMajorNote({ program }: { program: Program }) {
  return (
    <section role="note" className="rounded-xl border border-slate-300 bg-surface p-4 text-sm text-slate-700">
      <p className="font-semibold text-slate-900">
        Requirements for {program.name} aren&apos;t verified in Finish Line yet
      </p>
      <p className="mt-1">
        Your courses and plan are kept, and university and Gen Ed requirements are still checked. Finish Line
        won&apos;t check {program.name} major requirements or recommend a plan until they&apos;re added from the
        UMD catalog.
        {program.catalog_url && (
          <>
            {" "}
            <a href={program.catalog_url} className="underline">
              See the official requirements
            </a>
            .
          </>
        )}
      </p>
    </section>
  );
}
