import type { Metadata } from "next";
import DegreeProgressDashboard from "@/components/DegreeProgressDashboard";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Degree Progress" };

export default function ProgressPage() {
  return (
    <PageShell
      title="Degree Progress"
      description="What's complete, what's left, and which courses can fill each requirement."
      width="narrow"
    >
      <DegreeProgressDashboard />
    </PageShell>
  );
}
