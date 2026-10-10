import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { THEME_SCRIPT } from "@/lib/theme";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Finish Line", template: "%s · Finish Line" },
  description:
    "Your degree. Your plan. Your finish line. Degree requirements, prerequisites, and a semester-by-semester graduation plan for UMD Information Science.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // data-theme is set by THEME_SCRIPT before React hydrates, so the server
    // HTML can't match it; suppressHydrationWarning covers only this element.
    <html lang="en" className={`${geistSans.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
