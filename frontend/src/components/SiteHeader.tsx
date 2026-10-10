import Link from "next/link";
import NavLinks from "@/components/NavLinks";
import ThemeToggle from "@/components/ThemeToggle";

export function Logo() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-2 whitespace-nowrap">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-xs font-bold tracking-wide text-white">
        FL
      </span>
      <span className="text-lg font-semibold tracking-tight text-slate-900">Finish Line</span>
    </Link>
  );
}

export default function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-surface">
      {/* Phones: logo and theme toggle on one row, links scroll below.
          Wider screens: logo, links, toggle in one row. */}
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-2 gap-y-3 px-4 py-3 sm:flex-nowrap sm:px-6">
        <div className="order-1 mr-auto">
          <Logo />
        </div>
        <div className="order-3 w-full min-w-0 sm:order-2 sm:w-auto">
          <NavLinks />
        </div>
        <div className="order-2 sm:order-3">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
