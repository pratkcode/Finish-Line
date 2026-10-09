// The planning session lives on the server; this browser remembers its id.
const SESSION_KEY = "finishline.sessionId";

export function readSessionId(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function writeSessionId(id: string | null) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage unavailable: the plan still works until the page is closed.
  }
}
