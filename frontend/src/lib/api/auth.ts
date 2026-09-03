import { apiFetch } from "./client";
import type { AuthCredentials, Token, UserPublic, UserUpdateInput } from "@/lib/types/auth";

/** Client for `/api/v1/auth` on the FastAPI backend (Phase 8). */

export async function registerUser(payload: AuthCredentials): Promise<UserPublic> {
  return apiFetch<UserPublic>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginUser(payload: AuthCredentials): Promise<Token> {
  return apiFetch<Token>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** `credential` is the raw ID token Google Identity Services hands back to
 * the frontend -- the backend verifies it server-side before issuing a
 * StudyGraph access token. See backend/app/core/google_auth.py. */
export async function loginWithGoogle(credential: string): Promise<Token> {
  return apiFetch<Token>("/api/v1/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });
}

export async function getCurrentUser(): Promise<UserPublic> {
  return apiFetch<UserPublic>("/api/v1/auth/me");
}

export async function updateProfile(payload: UserUpdateInput): Promise<UserPublic> {
  return apiFetch<UserPublic>("/api/v1/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
