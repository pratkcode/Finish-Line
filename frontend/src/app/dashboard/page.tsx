import type { Metadata } from "next";
import Dashboard from "@/components/Dashboard";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <PageShell title="Dashboard" description="Your degree at a glance.">
      <Dashboard />
    </PageShell>
  );
}
