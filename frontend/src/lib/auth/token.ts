/**
 * Persists the JWT issued by `POST /api/v1/auth/login`. `client.ts` reads
 * this on every request so any tab with a valid token automatically attaches
 * `Authorization: Bearer <token>` -- see AuthProvider for the state that
 * wraps this for the UI.
 */

const STORAGE_KEY = "studygraph-token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  window.localStorage.setItem(STORAGE_KEY, token);
}

export function clearStoredToken(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}
