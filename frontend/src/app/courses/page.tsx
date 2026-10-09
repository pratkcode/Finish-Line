import type { Metadata } from "next";
import CourseBrowser from "@/components/CourseBrowser";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Courses" };

export default function CoursesPage() {
  return (
    <PageShell
      title="Courses"
      description="Search UMD Information Science courses and see what each one requires and unlocks."
    >
      <CourseBrowser />
    </PageShell>
  );
}
