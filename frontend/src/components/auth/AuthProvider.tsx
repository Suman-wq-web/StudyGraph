"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getCurrentUser, loginUser, loginWithGoogle, registerUser, updateProfile } from "@/lib/api/auth";
import { clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth/token";
import type { UserPublic, UserUpdateInput } from "@/lib/types/auth";

interface AuthContextValue {
  user: UserPublic | null;
  /** True until the initial token-validation check (on mount) resolves. */
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  /** Exchanges a verified Google ID token (from GoogleButton) for a
   * StudyGraph session, through the same token storage/user-state path as
   * `login`. */
  loginWithGoogle: (credential: string) => Promise<void>;
  logout: () => void;
  /** Persists a profile edit via PATCH /auth/me and updates `user` in place. */
  updateProfile: (payload: UserUpdateInput) => Promise<UserPublic>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Owns the Phase 8 session: on mount, validates any token already in
 * localStorage against `/auth/me` (so a stale/expired token doesn't leave
 * the UI thinking it's logged in), and exposes login/register/logout.
 * `client.ts` reads the token straight out of localStorage on every
 * request -- the state here is for the UI (current user, loading), not for
 * attaching the Authorization header.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!getStoredToken()) {
      setIsLoading(false);
      return;
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => {
        clearStoredToken();
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginUser({ email, password });
    setStoredToken(token.accessToken);
    setUser(await getCurrentUser());
  }, []);

  // Register has no response token (see backend/app/api/v1/auth.py), so log
  // the new user in immediately after to start their session the same way
  // a returning user's login does.
  const register = useCallback(
    async (email: string, password: string) => {
      await registerUser({ email, password });
      await login(email, password);
    },
    [login]
  );

  const handleLoginWithGoogle = useCallback(async (credential: string) => {
    const token = await loginWithGoogle(credential);
    setStoredToken(token.accessToken);
    setUser(await getCurrentUser());
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
  }, []);

  const handleUpdateProfile = useCallback(async (payload: UserUpdateInput) => {
    const updated = await updateProfile(payload);
    setUser(updated);
    return updated;
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        register,
        loginWithGoogle: handleLoginWithGoogle,
        logout,
        updateProfile: handleUpdateProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
