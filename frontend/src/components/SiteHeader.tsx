import Link from "next/link";
import NavLinks from "@/components/NavLinks";

export function Logo() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-2 whitespace-nowrap">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-700 text-xs font-bold tracking-wide text-white">
        FL
      </span>
      <span className="text-lg font-semibold tracking-tight text-slate-900">Finish Line</span>
    </Link>
  );
}

export default function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <Logo />
        <NavLinks />
      </div>
    </header>
  );
}
