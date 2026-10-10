"use client";

import { useEffect, useSyncExternalStore } from "react";
import { applyTheme, chooseTheme, currentTheme, storedTheme, systemTheme, type Theme } from "@/lib/theme";

// Re-render when <html data-theme> changes (this toggle, or the system setting).
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

export default function ThemeToggle() {
  // null while server rendering: the theme is only known in the browser.
  const theme = useSyncExternalStore<Theme | null>(subscribe, currentTheme, () => null);

  // Follow the operating system until the student picks a theme themselves.
  useEffect(() => {
    const query = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => storedTheme() === null && applyTheme(systemTheme());
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => chooseTheme(next)}
      aria-label={theme ? `Switch to ${next} mode` : "Switch color theme"}
      title={theme ? `Switch to ${next} mode` : "Switch color theme"}
      data-testid="theme-toggle"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
    >
      {/* Both icons render; CSS shows the right one, so there's no mismatch or flash. */}
      <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px] dark:hidden" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
      <svg aria-hidden viewBox="0 0 24 24" className="hidden h-[18px] w-[18px] dark:block" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    </button>
  );
}
