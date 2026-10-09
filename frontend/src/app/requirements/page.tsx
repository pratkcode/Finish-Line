import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import RequirementsChecklist from "@/components/RequirementsChecklist";

export const metadata: Metadata = { title: "Degree Requirements" };

export default function RequirementsPage() {
  return (
    <PageShell
      title="Degree Requirements"
      description="Every rule in the degree, from the UMD catalog, checked against your courses."
    >
      <RequirementsChecklist />
    </PageShell>
  );
}
