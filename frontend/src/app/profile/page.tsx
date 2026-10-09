import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import ProfileEditor from "@/components/ProfileEditor";

export const metadata: Metadata = { title: "Profile" };

export default function ProfilePage() {
  return (
    <PageShell
      title="Profile"
      description="Your program, semester, and completed courses. Saved in this browser; no account needed."
      width="narrow"
    >
      <ProfileEditor />
    </PageShell>
  );
}
