// Light/dark theme. The choice is stored in localStorage; with no stored
// choice the operating system's setting is used (and followed if it changes).

export type Theme = "light" | "dark";

export const THEME_KEY = "finishline.theme";

// Runs in <head> before the page paints, so the first frame already has the
// right theme. Kept tiny and dependency-free; it mirrors applyTheme below.
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.setAttribute("data-theme",t)}catch(e){document.documentElement.setAttribute("data-theme","light")}})();`;

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** Switch the page's theme at once (no staggered color transitions). */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.setAttribute("data-theme-switching", "");
  root.setAttribute("data-theme", theme);
  // Two frames: let the new colors paint before transitions return.
  requestAnimationFrame(() => requestAnimationFrame(() => root.removeAttribute("data-theme-switching")));
}

/** The student's explicit choice, remembered across visits. */
export function chooseTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage blocked (e.g. private mode): the choice lasts for this page only.
  }
  applyTheme(theme);
}
