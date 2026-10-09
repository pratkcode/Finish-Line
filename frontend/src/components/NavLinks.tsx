"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/graduation-plan", label: "Graduation Plan" },
  { href: "/progress", label: "Progress" },
  { href: "/courses", label: "Courses" },
  { href: "/requirements", label: "Requirements" },
  { href: "/profile", label: "Profile" },
];

export default function NavLinks() {
  const pathname = usePathname();
  return (
    // One scrollable row on small screens instead of wrapping onto several lines.
    <nav aria-label="Main" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex gap-1 text-sm font-medium whitespace-nowrap">
        {LINKS.map(({ href, label }) => {
          const active = pathname === href;
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-2.5 py-1.5 ${
                  active ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
