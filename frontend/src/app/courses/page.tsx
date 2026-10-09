import type { Metadata } from "next";
import CourseBrowser from "@/components/CourseBrowser";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Courses" };

export default function CoursesPage() {
  return (
    <PageShell
      title="Courses"
      description="Search the UMD undergraduate catalog across all departments and see what each course requires and unlocks."
    >
      <CourseBrowser />
    </PageShell>
  );
}
