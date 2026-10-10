import type { Metadata } from "next";
import GraduationPlanView from "@/components/GraduationPlanView";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Graduation Plan" };

export default function GraduationPlanPage() {
  return (
    <PageShell
      title="Graduation Plan"
      description="Your semester-by-semester plan. Build it yourself or start from a recommendation, then edit it however you like. A planning tool, not an official UMD schedule."
    >
      <GraduationPlanView />
    </PageShell>
  );
}
