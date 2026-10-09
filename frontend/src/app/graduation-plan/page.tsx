import type { Metadata } from "next";
import GraduationPlanView from "@/components/GraduationPlanView";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Graduation Plan" };

export default function GraduationPlanPage() {
  return (
    <PageShell
      title="Graduation Plan"
      description="A recommended path to graduation, generated from your courses. It's a planning tool, not an official UMD schedule."
    >
      <GraduationPlanView />
    </PageShell>
  );
}
