import type { Metadata } from "next";
import AcademicHistory from "@/components/AcademicHistory";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Academic History" };

export default function HistoryPage() {
  return (
    <PageShell
      title="Academic History"
      description="Semesters at UMD and other schools, courses in progress, transfer credit, and requirements met another way. Only verified items count toward your degree."
    >
      <AcademicHistory />
    </PageShell>
  );
}
